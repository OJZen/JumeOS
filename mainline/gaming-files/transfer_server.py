#!/usr/bin/env python3
"""Explicit, short-lived Wi-Fi sharing. No SimpleHTTPRequestHandler or CGI."""
import argparse
import collections
import ctypes
import errno
import email.utils
import http.cookies
import http.server
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import socketserver
import stat
import subprocess
import sys
import threading
import time
import urllib.parse

MAX_FILE = 8 * 1024**3
BLOCK = 64 * 1024
RESERVE = 16 * 1024**2
SESSION_SECONDS = 7200


def wifi_link():
    """Use NM activation, not the mere existence of an interface/IP or Ethernet."""
    env = dict(os.environ, LC_ALL="C")
    def nm(*args):
        return subprocess.run(["/usr/bin/nmcli", "-t", "--escape", "no", *args],
                              env=env, capture_output=True, text=True, timeout=2, check=True).stdout
    try:
        rows = nm("-f", "DEVICE,TYPE,STATE", "device", "status").splitlines()
        for row in rows:
            parts = row.split(":")
            if len(parts) != 3 or parts[1:] != ["wifi", "connected"] or not re.fullmatch(r"[\w.-]{1,15}", parts[0]):
                continue
            data = nm("-g", "GENERAL.TYPE,GENERAL.STATE,GENERAL.CON-PATH,IP4.ADDRESS", "device", "show", parts[0]).splitlines()
            if len(data) < 4 or data[0] != "wifi" or not data[1].startswith("100 "):
                continue
            for value in data[3:]:
                address = ipaddress.IPv4Interface(value)
                if not (address.ip.is_loopback or address.ip.is_link_local or address.ip.is_multicast or address.ip.is_unspecified):
                    return (parts[0], str(address), data[2])
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def components(path):
    if path == "":
        return []
    parts = path.split("/")
    if len(path.encode("utf-8")) > 4096 or len(parts) > 64:
        raise ValueError("路径过长")
    if any(not p or p.startswith(".") or "\\" in p or ":" in p or len(p.encode("utf-8")) > 255
           or any(ord(c) < 32 or ord(c) == 127 for c in p) for p in parts):
        raise ValueError("不允许此路径或隐藏文件")
    return parts


def directory(fd, path):
    current = os.dup(fd)
    try:
        for name in components(path):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = child
        return current
    except Exception:
        os.close(current)
        raise


def open_root(path):
    path = os.path.abspath(path)
    if path in ("/", str(Path.home()), "/tmp", "/run", "/home", "/media", "/mnt"):
        raise ValueError("请选择专用共享目录，不共享整个用户或系统目录")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        root = directory(fd, path.lstrip("/"))
    finally:
        os.close(fd)
    if os.fstat(root).st_uid != os.geteuid() and not (path == "/roms" or path.startswith("/roms/")):
        os.close(root)
        raise ValueError("请选择自己的目录或游戏目录")
    return root


def publish(fd, temporary, name):
    # Linux renameat2 supports no-overwrite publication on removable FAT too.
    libc = ctypes.CDLL(None, use_errno=True)
    if not hasattr(libc, "renameat2"):
        # Host fixture fallback; link() also refuses existing destinations.
        os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        os.unlink(temporary, dir_fd=fd)
        return
    rename = libc.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(fd, os.fsencode(temporary), fd, os.fsencode(name), 1):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


class ShareServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = False
    allow_reuse_address = False
    request_queue_size = 4

    def __init__(self, root, link_provider=wifi_link, event=lambda value: None):
        self.provider, self.event = link_provider, event
        self.link = link_provider()
        if not self.link:
            raise ValueError("请先连接 Wi-Fi，并获取 IPv4 地址")
        self.address = ipaddress.IPv4Interface(self.link[1])
        self.root_path = os.path.abspath(root)
        self.root_fd = open_root(root)
        self.root_identity = os.fstat(self.root_fd)
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(4)
        self.transfers = threading.BoundedSemaphore(2)
        self.sockets = set()
        self.attempts = collections.deque(maxlen=6)
        self.token = secrets.token_urlsafe(24)
        self.code = f"{secrets.randbelow(100000000):08d}"
        self.cookie = secrets.token_urlsafe(32)
        try:
            super().__init__((str(self.address.ip), 0), Handler)
        except Exception:
            os.close(self.root_fd)
            raise
        self.started = self.checked = time.monotonic()
        self.host = f"{self.address.ip}:{self.server_port}"
        self.origin = "http://" + self.host

    def server_bind(self):
        # HTTPServer resolves a reverse hostname here; this numeric-only LAN
        # service does not use it. Slow router DNS must not expire startup health.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    def healthy(self):
        try:
            now = time.monotonic()
            info = os.stat(self.root_path, follow_symlinks=False)
            return not self.stop_event.is_set() and now - self.checked < 4 and now - self.started < SESSION_SECONDS and (info.st_dev, info.st_ino) == (self.root_identity.st_dev, self.root_identity.st_ino)
        except OSError:
            return False

    def monitor(self):
        while not self.stop_event.wait(1):
            if self.provider() != self.link or not self.healthy():
                self.event({"state": "stopped", "message": "Wi-Fi、共享目录发生变化或会话已到期，请重新开启"})
                self.halt()
                return
            self.checked = time.monotonic()

    def halt(self):
        self.stop_event.set()
        with self.lock:
            for connection in tuple(self.sockets):
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def process_request(self, request, client_address):
        if not self.healthy() or ipaddress.ip_address(client_address[0]) not in self.address.network or not self.slots.acquire(False):
            request.close()
            return
        with self.lock:
            self.sockets.add(request)
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self.lock:
                self.sockets.discard(request)
            self.slots.release()

    def handle_error(self, request, client_address):
        pass  # Never log request URLs, cookies, local filenames or credentials.

    def run(self):
        watcher = threading.Thread(target=self.monitor, daemon=True)
        watcher.start()
        self.timeout = .25
        try:
            while not self.stop_event.is_set():
                self.handle_request()
        finally:
            self.halt()
            self.server_close()  # Join handlers after socket shutdown; remove partial uploads.
            watcher.join(5)
            os.close(self.root_fd)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # Exactly one bounded request per connection; no pipelining.
    server_version = "JumeTransfer"
    sys_version = ""

    def setup(self):
        self.responded = False
        self.request.settimeout(15)
        super().setup()

    def send_response(self, code, message=None):
        self.responded = True
        super().send_response(code, message)

    def log_message(self, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self.reply(code, {"error": message or "请求未完成"})

    def reply(self, code, value, content_type="application/json; charset=utf-8", headers=None):
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.common_headers()
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def common_headers(self):
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")

    def authenticated(self):
        try:
            cookie = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
            return "jume" in cookie and secrets.compare_digest(cookie["jume"].value, self.server.cookie)
        except (http.cookies.CookieError, TypeError):
            return False

    def route(self):
        server = self.server
        if len(self.path) > 8192 or sum(len(k) + len(v) for k, v in self.headers.items()) > 16384:
            self.reply(431, {"error": "请求头过大"}); return
        if self.headers.get_all("Host") != [server.host] or not self.path.startswith("/") or self.path.startswith("//"):
            self.reply(403, {"error": "请使用掌机显示的地址"}); return
        if self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) > 1:
            self.reply(400, {"error": "不支持此请求格式"}); return
        if not server.healthy():
            self.reply(503, {"error": "Wi-Fi 共享已停止"}); return
        if self.headers.get("Origin") not in (None, server.origin) or self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.reply(403, {"error": "拒绝跨站请求"}); return
        parsed = urllib.parse.urlsplit(self.path)
        args = urllib.parse.parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True, max_num_fields=4, errors="strict")
        if any(len(v) != 1 for v in args.values()):
            raise ValueError("参数重复")
        args = {k: v[0] for k, v in args.items()}
        assets = {"/": ("transfer.html", "text/html; charset=utf-8"), "/app.js": ("transfer.js", "text/javascript; charset=utf-8"), "/app.css": ("transfer.css", "text/css; charset=utf-8")}
        if self.command == "GET" and parsed.path in assets:
            name, kind = assets[parsed.path]
            self.reply(200, Path(__file__).with_name(name).read_bytes(), kind); return
        if self.command == "POST" and parsed.path == "/api/session":
            if self.headers.get("Origin") != server.origin or self.headers.get("Content-Type") != "application/json":
                self.reply(403, {"error": "请从本机传输页面连接"}); return
            size = self.length(256)
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("连接码格式错误")
            supplied = body.get("code", "")
            if not isinstance(supplied, str) or not supplied.isascii():
                raise ValueError("连接码格式错误")
            with server.lock:
                now = time.monotonic()
                while server.attempts and now - server.attempts[0] > 60:
                    server.attempts.popleft()
                if len(server.attempts) >= 6:
                    self.reply(429, {"error": "尝试过多，请等待一分钟"}); return
                if not (secrets.compare_digest(supplied, server.token) or secrets.compare_digest(supplied, server.code)):
                    server.attempts.append(now)
                    self.reply(403, {"error": "连接码不正确"}); return
            self.reply(200, {"ok": True}, headers={"Set-Cookie": f"jume={server.cookie}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_SECONDS}"}); return
        if not self.authenticated():
            self.reply(401, {"error": "请先输入掌机连接码"}); return
        if self.command == "GET" and parsed.path == "/api/status":
            self.reply(200, {"ok": True})
        elif self.command == "GET" and parsed.path == "/api/list":
            folder = args.get("path", "")
            offset = int(args.get("offset", "0"))
            if not 0 <= offset <= 10000:
                raise ValueError("目录页码超限")
            fd = directory(server.root_fd, folder)
            try:
                rows, count, more = [], 0, False
                with os.scandir(fd) as entries:
                    for entry in entries:
                        if count >= 10000:
                            break
                        if entry.name.startswith(".") or entry.is_symlink():
                            continue
                        info = entry.stat(follow_symlinks=False)
                        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                            continue
                        count += 1
                        if count <= offset:
                            continue
                        if len(rows) == 200:
                            more = True; break
                        rows.append({"name": entry.name, "directory": stat.S_ISDIR(info.st_mode), "size": info.st_size, "modified": int(info.st_mtime)})
                space = os.fstatvfs(fd)
                self.reply(200, {"files": rows, "next": offset + len(rows) if more else None, "limited": count >= 10000,
                                 "free": space.f_bavail * space.f_frsize, "maxFile": MAX_FILE,
                                 "writable": os.access(".", os.W_OK, dir_fd=fd, effective_ids=True), "rootName": Path(server.root_path).name})
            finally:
                os.close(fd)
        elif self.command == "PUT" and parsed.path == "/api/upload":
            if self.headers.get("Origin") != server.origin:
                self.reply(403, {"error": "拒绝跨站上传"}); return
            self.upload(args)
        elif self.command in ("GET", "HEAD") and parsed.path == "/api/download":
            self.download(args)
        else:
            self.reply(404, {"error": "未提供此操作"})

    def length(self, maximum):
        value = self.headers.get("Content-Length", "")
        if not value.isascii() or not value.isdigit() or len(value) > 12 or int(value) > maximum:
            raise ValueError("文件/请求大小超限或长度缺失")
        return int(value)

    def upload(self, args):
        size = self.length(MAX_FILE)
        name = args.get("name", "")
        if len(components(name)) != 1:
            raise ValueError("文件名无效")
        if not self.server.transfers.acquire(False):
            self.reply(429, {"error": "已有两个传输任务，请稍后重试"}); return
        parent, fd, temporary = None, None, None
        try:
            parent = directory(self.server.root_fd, args.get("path", ""))
            try:
                os.stat(name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise FileExistsError()
            space = os.fstatvfs(parent)
            if size + RESERVE > space.f_bavail * space.f_frsize:
                self.reply(507, {"error": "空间不足，需保留 16 MiB"}); return
            temporary = ".jume-upload-" + secrets.token_hex(12)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            received, reported, last = 0, 0, 0.
            with os.fdopen(fd, "wb") as output:
                fd = None
                while received < size:
                    if not self.server.healthy():
                        raise ConnectionAbortedError()
                    block = self.rfile.read(min(BLOCK, size - received))
                    if not block:
                        raise ConnectionAbortedError()
                    output.write(block); received += len(block)
                    if received - reported >= 4 * 1024**2:
                        reported = received
                        space = os.fstatvfs(parent)
                        if space.f_bavail * space.f_frsize < RESERVE:
                            raise OSError(errno.ENOSPC, "space")
                    now = time.monotonic()
                    if now - last >= .5:
                        self.server.event({"state": "progress", "direction": "upload", "done": received, "total": size}); last = now
                output.flush(); os.fsync(output.fileno())
            if not self.server.healthy():
                raise ConnectionAbortedError()
            publish(parent, temporary, name)
            self.reply(201, {"ok": True})
            self.server.event({"state": "complete", "direction": "upload", "total": size})
        finally:
            if fd is not None:
                os.close(fd)
            if temporary and parent is not None:
                try: os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError: pass
            if parent is not None:
                os.close(parent)
            self.server.transfers.release()

    def download(self, args):
        parts = components(args.get("path", ""))
        if not parts:
            raise ValueError("请选择文件")
        if not self.server.transfers.acquire(False):
            self.reply(429, {"error": "传输繁忙"}); return
        fd = None
        try:
            parent = directory(self.server.root_fd, "/".join(parts[:-1]))
            try: fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            finally: os.close(parent)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("仅可下载普通文件")
            start, end, code = 0, info.st_size - 1, 200
            etag = f'"{info.st_mtime_ns:x}-{info.st_size:x}"'
            requested = self.headers.get("Range")
            if self.headers.get("If-Range") not in (None, etag):
                requested = None
            if requested:
                match = re.fullmatch(r"bytes=(\d+)-(\d*)", requested)
                if not match or not info.st_size:
                    self.reply(416, {"error": "无效范围"}); return
                start = int(match[1]); end = min(end, int(match[2])) if match[2] else end
                if start > end:
                    self.reply(416, {"error": "无效范围"}); return
                code = 206
            count = max(0, end - start + 1)
            self.send_response(code); self.common_headers()
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("ETag", etag)
            self.send_header("Last-Modified", email.utils.formatdate(info.st_mtime, usegmt=True))
            self.send_header("Content-Disposition", "attachment; filename=download; filename*=UTF-8''" + urllib.parse.quote(parts[-1], safe=""))
            self.send_header("Content-Length", str(count)); self.send_header("Accept-Ranges", "bytes")
            if code == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{info.st_size}")
            self.end_headers()
            if self.command == "HEAD":
                return
            os.lseek(fd, start, os.SEEK_SET); sent, last = 0, 0.
            while sent < count:
                if not self.server.healthy():
                    raise ConnectionAbortedError()
                block = os.read(fd, min(BLOCK, count - sent))
                if not block:
                    raise ConnectionAbortedError()
                self.wfile.write(block); sent += len(block)
                now = time.monotonic()
                if now - last >= .5:
                    self.server.event({"state": "progress", "direction": "download", "done": sent, "total": count}); last = now
            self.server.event({"state": "complete", "direction": "download", "total": count})
        finally:
            if fd is not None: os.close(fd)
            self.server.transfers.release()

    def dispatch(self):
        try:
            self.route()
        except (BrokenPipeError, ConnectionError, TimeoutError):
            pass
        except FileExistsError:
            if not self.responded: self.reply(409, {"error": "同名文件已存在；不会覆盖，请重命名后上传"})
        except (ValueError, UnicodeError, json.JSONDecodeError):
            if not self.responded: self.reply(400, {"error": "无效路径或请求"})
        except OSError as error:
            if not self.responded: self.reply(507 if error.errno == errno.ENOSPC else 403, {"error": "无法访问文件；请检查权限、空间与存储设备"})

    do_GET = do_HEAD = do_POST = do_PUT = dispatch


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--probe", action="store_true")
    args.add_argument("--root")
    options = args.parse_args()
    output_lock = threading.Lock()
    def event(value):
        with output_lock:
            print(json.dumps(value, ensure_ascii=False), flush=True)
    if options.probe:
        link = wifi_link()
        event({"connected": bool(link), "address": str(ipaddress.IPv4Interface(link[1]).ip) if link else ""})
        return
    if os.geteuid() == 0 or not options.root:
        event({"state": "error", "message": "必须以普通用户选择共享目录"}); return
    try:
        server = ShareServer(options.root, event=event)
    except (ValueError, OSError) as error:
        event({"state": "error", "message": str(error)}); return
    signal.signal(signal.SIGTERM, lambda *args: server.halt())
    signal.signal(signal.SIGINT, lambda *args: server.halt())
    def parent_watch():
        sys.stdin.readline()  # Stop command or parent EOF both revoke the session.
        server.halt()
    threading.Thread(target=parent_watch, daemon=True).start()
    event({"state": "ready", "url": server.origin, "link": server.origin + "/#" + server.token, "code": server.code})
    server.run()


if __name__ == "__main__":
    main()
