#!/usr/bin/env python3
"""Real loopback HTTP and disposable files; no real Wi-Fi or user data."""
import http.client
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.parse

spec = importlib.util.spec_from_file_location("transfer_server", os.environ.get("JUME_TRANSFER_MODULE", Path(__file__).with_name("transfer_server.py")))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TransferCheck(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jume-transfer-")
        self.root = Path(self.temp.name) / "shared"
        self.root.mkdir()
        self.link = ("fixture-wifi", "127.0.0.1/8", "fixture-connection")
        with patch('socket.getfqdn', side_effect=AssertionError('No reverse DNS for a numeric LAN listener')):
            self.server = module.ShareServer(str(self.root), lambda: self.link)
        self.thread = threading.Thread(target=self.server.run)
        self.thread.start()

    def tearDown(self):
        self.server.halt()
        self.thread.join(5)
        self.assertFalse(self.thread.is_alive())
        self.temp.cleanup()

    def request(self, method, path, data=None, auth=True, headers=None):
        h = {"Host": self.server.host, "Origin": self.server.origin}
        if auth:
            h["Cookie"] = "jume=" + self.server.cookie
        h.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        connection.request(method, path, data, h)
        response = connection.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        connection.close()
        return result

    def login(self, code):
        return self.request("POST", "/api/session", json.dumps({"code":code}), False, {"Content-Type":"application/json"})

    def wait(self, condition):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if condition(): return
            time.sleep(.02)
        self.fail("bounded condition did not complete")

    def test_wifi_gate(self):
        with self.assertRaises(ValueError):
            module.ShareServer(str(self.root), lambda: None)
        def nm(*args, **kwargs):
            class Output: stdout = "eth0:ethernet:connected\nwlan0:wifi:disconnected\n"
            return Output()
        with patch.object(module.subprocess, "run", nm):
            self.assertIsNone(module.wifi_link())
        self.link = None
        self.wait(lambda: not self.thread.is_alive())
        self.assertFalse(self.server.healthy())

    def test_wifi_nm_activation(self):
        def nm(command, **kwargs):
            class Output: stdout = "wlan0:wifi:connected\n"
            if "show" in command:
                Output.stdout = "wifi\n100 (connected)\n/org/freedesktop/NetworkManager/ActiveConnection/4\n192.168.31.7/24\n"
            return Output()
        with patch.object(module.subprocess, "run", nm):
            self.assertEqual(module.wifi_link(), ("wlan0", "192.168.31.7/24", "/org/freedesktop/NetworkManager/ActiveConnection/4"))
        self.link = ("fixture-wifi", "127.0.0.2/8", "replacement")
        self.wait(lambda: not self.thread.is_alive())

    def test_parent_eof_revokes_service(self):
        if os.geteuid() == 0:
            self.skipTest("CLI deliberately refuses root; run the suite as nobody")
        source = str(module.__file__)
        script = "import importlib.util,sys; s=importlib.util.spec_from_file_location('transfer',sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); base=m.ShareServer; m.ShareServer=lambda root,event:base(root,lambda:('fixture','127.0.0.1/8','fixture'),event); sys.argv=[sys.argv[1],'--root',sys.argv[2]]; m.main()"
        child = subprocess.Popen([sys.executable,"-B","-c",script,source,str(self.root)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        try:
            record = json.loads(child.stdout.readline())
            self.assertEqual(record["state"], "ready")
            child.stdin.close()
            self.assertEqual(child.wait(timeout=5), 0)
        finally:
            if child.poll() is None: child.kill(); child.wait(timeout=3)
            child.stdout.close()

    def test_pairing_and_origin(self):
        self.assertEqual(self.request("GET", "/")[0], 200)
        self.assertEqual(self.request("GET", "/api/list", auth=False)[0], 401)
        code, headers, _ = self.login(self.server.code)
        self.assertEqual(code, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        self.assertEqual(self.login(self.server.token)[0], 200)
        self.assertEqual(self.request("GET", "/api/list", headers={"Host":"evil.example"})[0], 403)
        self.assertEqual(self.request("PUT", "/api/upload?name=bad", b"a", headers={"Origin":"http://evil.example"})[0], 403)
        self.assertEqual(self.request("GET", "/api/list", headers={"Sec-Fetch-Site":"cross-site"})[0], 403)
        for _ in range(6): self.assertEqual(self.login("wrong")[0], 403)
        self.assertEqual(self.login("wrong")[0], 429)

    def test_upload_download_and_no_overwrite(self):
        (self.root / "folder").mkdir()
        payload = b"Jume fixture\x00" * 20000
        query = urllib.parse.urlencode({"path":"folder", "name":"中文 <test>.bin"})
        self.assertEqual(self.request("PUT", "/api/upload?" + query, payload)[0], 201)
        self.assertEqual(self.request("PUT", "/api/upload?" + query, b"overwrite")[0], 409)
        url = "/api/download?" + urllib.parse.urlencode({"path":"folder/中文 <test>.bin"})
        code, headers, body = self.request("GET", url)
        self.assertEqual(code, 200); self.assertEqual(body, payload)
        self.assertTrue(headers["Content-Disposition"].startswith("attachment;"))
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.request("GET", url, headers={"Range":"bytes=3-18","If-Range":"stale"})[2],payload)
        code, _, body = self.request("GET", url, headers={"Range":"bytes=3-18"})
        self.assertEqual(code, 206); self.assertEqual(body, payload[3:19])
        self.assertEqual(self.request("GET", url, headers={"Range":"bytes=9999999-"})[0], 416)
        self.assertEqual(self.request("HEAD", url)[2], b"")
        self.assertEqual(self.request("PUT", "/api/upload?name=empty.txt", b"")[0], 201)
        self.assertEqual(self.request("GET", "/api/status")[0], 200)
        listing = json.loads(self.request("GET", "/api/list")[2])
        self.assertEqual({f["name"] for f in listing["files"]}, {"folder", "empty.txt"})
        self.assertFalse(list(self.root.rglob(".jume-upload-*")))

    def test_paths_and_hidden_files(self):
        secret = Path(self.temp.name) / "private.txt"; secret.write_bytes(b"not shared")
        (self.root / "link").symlink_to(secret)
        (self.root / "dirlink").symlink_to(secret.parent, target_is_directory=True)
        (self.root / ".private").write_bytes(b"hidden")
        for path in ("../private.txt", str(secret), ".private", "a/../../private.txt", "..\\private.txt"):
            url = "/api/download?" + urllib.parse.urlencode({"path":path})
            self.assertEqual(self.request("GET", url)[0], 400)
        for path in ("link", "dirlink/private.txt"):
            self.assertEqual(self.request("GET", "/api/download?path=" + path)[0], 403)
        self.assertEqual(json.loads(self.request("GET", "/api/list")[2])["files"], [])
        self.assertEqual(self.request("PUT", "/api/upload?name=..%2Fescaped", b"x")[0], 400)
        self.assertEqual(secret.read_bytes(), b"not shared")

    def test_disconnect_cleans_partial(self):
        connection = socket.create_connection(("127.0.0.1", self.server.server_port))
        headers = f"PUT /api/upload?name=incomplete HTTP/1.1\r\nHost: {self.server.host}\r\nOrigin: {self.server.origin}\r\nCookie: jume={self.server.cookie}\r\nContent-Length: 999999\r\n\r\n"
        connection.sendall(headers.encode() + b"partial" * 100)
        self.wait(lambda: bool(list(self.root.glob(".jume-upload-*"))))
        connection.close()
        self.wait(lambda: not list(self.root.glob(".jume-upload-*")))
        self.assertFalse((self.root / "incomplete").exists())

    def test_wifi_loss_interrupts_upload(self):
        connection = socket.create_connection(("127.0.0.1", self.server.server_port))
        headers = f"PUT /api/upload?name=interrupted HTTP/1.1\r\nHost: {self.server.host}\r\nOrigin: {self.server.origin}\r\nCookie: jume={self.server.cookie}\r\nContent-Length: 999999\r\n\r\n"
        connection.sendall(headers.encode() + b"x" * 70000)
        self.wait(lambda: bool(list(self.root.glob(".jume-upload-*"))))
        self.link = None
        self.wait(lambda: not self.thread.is_alive())
        connection.close()
        self.assertFalse((self.root / "interrupted").exists())
        self.assertFalse(list(self.root.glob(".jume-upload-*")))

    def test_storage_identity_and_session_expiry(self):
        old = self.root.with_name("old")
        self.root.rename(old); self.root.mkdir()
        self.assertFalse(self.server.healthy())
        self.wait(lambda: not self.thread.is_alive())
        self.assertFalse(list(self.root.iterdir()))

    def test_limits_and_pagination(self):
        for i in range(205): (self.root / f"file-{i}.txt").touch()
        first = json.loads(self.request("GET", "/api/list")[2])
        second = json.loads(self.request("GET", "/api/list?offset=200")[2])
        self.assertEqual(len(first["files"]), 200); self.assertEqual(first["next"], 200)
        self.assertEqual(len(second["files"]), 5); self.assertIsNone(second["next"])
        self.assertEqual(self.request("GET", "/api/list?offset=999999")[0], 400)
        self.assertEqual(self.request("PUT", "/api/upload?name=huge", b"", headers={"Content-Length":str(module.MAX_FILE + 1)})[0], 400)
        self.server.started -= module.SESSION_SECONDS
        self.assertFalse(self.server.healthy())


if __name__ == "__main__":
    unittest.main()
