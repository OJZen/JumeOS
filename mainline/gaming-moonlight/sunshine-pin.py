#!/usr/bin/env python3
"""Submit an operator-entered PIN to the isolated, manually started local Sunshine."""
import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import re
import ssl
import stat
import sys
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_directory", type=Path)
    parser.add_argument("--check", action="store_true", help="Check local TLS/authentication without entering a PIN")
    args = parser.parse_args()
    if not args.check and not sys.stdin.isatty():
        print("请在独立 Terminal 中运行此工具，PIN 只接受隐藏的终端输入。")
        return 2
    directory = args.private_directory
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("private directory")
    for name in ("operator.json", "server.crt"):
        info = (directory / name).lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("private file")
    credentials = json.loads((directory / "operator.json").read_text())
    authorization = base64.b64encode((credentials["username"] + ":" + credentials["password"]).encode()).decode()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False  # Trust the exact certificate created for this local test server.
    context.load_verify_locations(cafile=str(directory / "server.crt"))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
    headers = {"Authorization": "Basic " + authorization, "Content-Type": "application/json"}

    def request(path, data=None):
        body = None if data is None else json.dumps(data).encode()
        req = urllib.request.Request("https://127.0.0.1:47990/api/" + path, data=body, headers=headers)
        with opener.open(req, timeout=5) as response:
            return json.loads(response.read(65536))

    token = request("csrf-token")["csrf_token"]
    if not isinstance(token, str) or not token:
        raise ValueError("CSRF token")
    if args.check:
        print("SUNSHINE_LOCAL_AUTH_PASS")
        return 0
    pin = getpass.getpass("请输入掌机显示的 4 位 PIN（输入隐藏）：")
    if not re.fullmatch(r"[0-9]{4}", pin):
        print("PIN 必须为 4 位数字。")
        return 2
    headers["X-CSRF-Token"] = token
    accepted = request("pin", {"pin": pin, "name": "R46H Desktop"}).get("status") is True
    print("配对请求已提交，请查看掌机结果。" if accepted else "没有匹配的配对请求，请在掌机重新开始配对。")
    return 0 if accepted else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError):
        # Never echo credentials, request data, or protocol responses in diagnostics.
        print("无法连接临时 Sunshine，请检查它是否运行及私有状态是否完整。")
        raise SystemExit(1)
