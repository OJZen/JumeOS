#!/usr/bin/env python3
"""Focused host gates for the guarded R46H remote-screen feature."""

from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zlib


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "mainline/gaming-remote-screen"
FETCHER_PATH = ROOT / "fetch-screen.py"

def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


PNG_RAW = (b"\x00" + b"\x00" * (1024 * 3)) * 768
PNG = (
    b"\x89PNG\r\n\x1a\n"
    + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1024, 768, 8, 2, 0, 0, 0))
    + png_chunk(b"IDAT", zlib.compress(PNG_RAW))
    + png_chunk(b"IEND", b"")
)


def load_fetcher():
    spec = importlib.util.spec_from_file_location("r46h_remote_screen_fetcher", FETCHER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load remote-screen fetcher")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def requested_test_tmpdir() -> str | None:
    requested = os.environ.get("R46H_TEST_TMPDIR")
    if requested:
        Path(requested).mkdir(parents=True, exist_ok=True)
    return requested


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RemoteScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fetcher = load_fetcher()
        cls.capture_source = (ROOT / "r46h-drm-capture.c").read_text(encoding="utf-8")
        cls.build_script = (ROOT / "build-drm-capture.sh").read_text(encoding="utf-8")
        cls.helper = (ROOT / "r46h-screenshot").read_text(encoding="utf-8")
        cls.gateway = (ROOT / "r46h-screenshot-ssh").read_text(encoding="utf-8")
        cls.sudoers = (ROOT / "r46h-remote-screen.sudoers").read_text(encoding="utf-8")
        cls.installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        cls.rollback = (ROOT / "rollback.sh").read_text(encoding="utf-8")
        cls.fetcher_source = FETCHER_PATH.read_text(encoding="utf-8")

    def test_feature_leaves_accepted_ozone_config_and_launcher_untouched(self) -> None:
        self.assertFalse((ROOT / "retroarch.cfg").exists())
        self.assertFalse((ROOT / "r46h-game-ui").exists())
        for source in (self.installer, self.rollback):
            self.assertIn(
                "CONFIG_SHA256=0694b9f41220983bdf9d60789b97b2fe115f68474f22f4869a2764513bcf1835",
                source,
            )
            self.assertIn(
                "RUNNER_SHA256=b0a44a7184cef97e2b9597f0d84adacb66617073f9422ef719d98e3465cc77c8",
                source,
            )
            self.assertNotIn("CONFIG_SOURCE=", source)
            self.assertNotIn("RUNNER_SOURCE=", source)
            self.assertNotIn("systemctl stop r46h-gaming-frontend", source)
            self.assertNotIn("systemctl start r46h-gaming-frontend", source)

    def test_capture_is_one_bounded_kms_frame_and_drops_root_before_png(self) -> None:
        for token in (
            'dlopen("/usr/lib/aarch64-linux-gnu/libdrm.so.2"',
            '"drmModeGetResources"',
            '"drmModeGetCrtc"',
            '"drmModeGetFB2"',
            '"drmPrimeHandleToFD"',
            '"drmModeMapDumbBuffer"',
            "DRM_FORMAT_XRGB8888",
            "EXPECTED_WIDTH 1024U",
            "EXPECTED_HEIGHT 768U",
            'open("/dev/dri/card0", O_RDWR | O_CLOEXEC)',
            'strcmp(sudo_user, "ark")',
            "capture output must be one empty private ark file",
            "setgroups(0U, NULL)",
            "setgid(ARK_GID)",
            "setuid(ARK_UID)",
            "PR_SET_NO_NEW_PRIVS",
            "drop_to_ark();",
            "write_png(rgb, EXPECTED_WIDTH, EXPECTED_HEIGHT);",
        ):
            self.assertIn(token, self.capture_source)
        self.assertLess(
            self.capture_source.index("drop_to_ark();"),
            self.capture_source.index("write_png(rgb"),
        )
        for forbidden in ("system(", "popen(", "fork(", "socket(", "execl("):
            self.assertNotIn(forbidden, self.capture_source)

    def test_capture_build_is_offline_reproducible_and_hardened(self) -> None:
        for token in (
            "sha256:3686fd20408cf746c1171e9345fd6c842a71f87e589f691b2455435b3bdd141a",
            "EXPECTED_SHA256=77f22181289edd701001fd6570a49afbfde277417e3769a693d1dd335cad324e",
            "--network none",
            "--pull never",
            "--read-only",
            "-fPIE -pie",
            "-D_FORTIFY_SOURCE=3",
            "-fstack-protector-strong",
            "-Wl,-z,relro,-z,now",
            "-Wl,--build-id=none",
            "-ffile-prefix-map=/src=.",
            "Machine:                           AArch64",
            "ld-linux-aarch64.so.1 libc.so.6 libz.so.1",
        ):
            self.assertIn(token, self.build_script)
        self.assertNotIn("--network host", self.build_script)

    def test_target_helper_exposes_only_capture_and_exact_export_removal(self) -> None:
        for token in (
            "EXPECTED_ROOT_UUID=d3130007-46a4-4d56-9001-000000000007",
            "MAX_PNG_BYTES=16777216",
            "MAX_PENDING_EXPORTS=8",
            "count < MAX_PENDING_EXPORTS",
            "CAPTURE_BINARY=/usr/local/libexec/r46h-drm-capture",
            "EXPECTED_CAPTURE_SHA256=77f22181289edd701001fd6570a49afbfde277417e3769a693d1dd335cad324e",
            "expected exactly one supported gaming frontend process",
            "pgrep -u 1000 -f '^/usr/bin/retroarch( |$)'",
            "pgrep -u 1000 -f '^/opt/r46h/es-de/bin/es-de( |$)'",
            "${#retroarch_pids[@]} <= 1",
            "${#es_de_pids[@]} <= 1",
            "${#retroarch_pids[@]} + ${#es_de_pids[@]} >= 1",
            "SUDOERS=/etc/sudoers.d/r46h-remote-screen",
            '/usr/bin/sudo -n -- "$CAPTURE_BINARY"',
            "89504e470d0a1a0a",
            "0000000049454e44ae426082",
            "another screenshot operation is active",
            "r46h-screen-$(date -u +%Y%m%dT%H%M%SZ)-$$.png",
            "R46H_SCREENSHOT_REMOVE result=pass",
            "--read) read_export",
        ):
            self.assertIn(token, self.helper)
        self.assertEqual(self.helper.count('/usr/bin/sudo -n -- "$CAPTURE_BINARY"'), 1)
        self.assertNotIn("r46h-retroarch-command", self.helper)
        self.assertNotIn("SCREENSHOT\\n", self.helper)
        self.assertNotIn("gaming-ozone-fbneo-v0.1-installed", self.helper)
        self.assertNotIn("remote-screen-v0.1-installed", self.helper)
        self.assertNotIn('sha256sum "$SUDOERS"', self.helper)
        self.assertNotIn("network_cmd", self.helper)
        self.assertNotIn("pgrep -u 1000 -x retroarch", self.helper)
        self.assertNotIn("pgrep -u 1000 -x es-de", self.helper)
        self.assertNotIn("eval ", self.helper)
        self.assertNotIn("rm -rf", self.helper)

    def test_dedicated_ssh_key_is_forced_to_three_bounded_operations(self) -> None:
        for token in (
            "SSH_ORIGINAL_COMMAND",
            "SSH_CONNECTION",
            "SSH_TTY",
            '"$HELPER")',
            "(--read|--remove)",
            'exec "$HELPER"',
            "screenshot key does not authorize this command",
        ):
            self.assertIn(token, self.gateway)
        self.assertNotIn("eval ", self.gateway)
        self.assertNotIn("bash -c", self.gateway)
        self.assertIn('restrict,command=\\"/usr/local/bin/r46h-screenshot-ssh\\"', self.installer)
        self.assertIn("already has broader authorization", self.installer)
        self.assertEqual(
            self.sudoers,
            'ark ALL=(root) NOPASSWD: /usr/local/libexec/r46h-drm-capture ""\n',
        )

    def test_transaction_is_exact_accepted_ozone_successor_and_has_key_rollback(self) -> None:
        expected_hashes = {
            "BASE_RECEIPT_SHA256": "82721e16a9b9a7c7927d0ca4d228dd3d850e3a39dca245177ec1f016b3b8d314",
            "OZONE_RECEIPT_SHA256": "8acac2c8b8e4295c0235ad1fc7e396e341dcc4b1ba771a053355a98cf8fb73ec",
            "CONFIG_SHA256": sha256(REPO / "mainline/gaming-ozone-fbneo/retroarch.cfg"),
            "RUNNER_SHA256": sha256(REPO / "mainline/gaming-ozone-fbneo/r46h-game-ui"),
            "CAPTURE_SHA256": "bb4c421029085cc182c369bb8b7c4a1431d0de2ddafb244d8c347dbbad127618",
            "HELPER_SHA256": "728ad68187cc5647c695014c61ec86f48207ef05b46088463d427832ee3e40e4",
            "GATEWAY_SHA256": sha256(ROOT / "r46h-screenshot-ssh"),
            "SUDOERS_SHA256": sha256(ROOT / "r46h-remote-screen.sudoers"),
            "ROLLBACK_SHA256": sha256(ROOT / "rollback.sh"),
        }
        for name, digest in expected_hashes.items():
            marker = f"readonly {name}={digest}"
            with self.subTest(name=name):
                self.assertIn(marker, self.installer)
                if name not in ("BASE_RECEIPT_SHA256", "ROLLBACK_SHA256"):
                    self.assertIn(marker, self.rollback)
        for token in (
            "EXPECTED_ROOT_UUID=d3130007-46a4-4d56-9001-000000000007",
            "operator.pub",
            "ssh-ed25519",
            "r46h-remote-screen-v0.1",
            "ozone_receipt_sha256",
            "key-added",
            "remove_key_line",
            "frontend_untouched=active",
            "rollback state retained",
            "/usr/sbin/visudo -cf",
            "$CAPTURE_SOURCE:$CAPTURE_SHA256",
            "$SUDOERS_SOURCE:$SUDOERS_SHA256",
        ):
            self.assertIn(token, self.installer)
        expected_payload = (
            "$'install.sh\\noperator.pub\\nr46h-drm-capture\\n"
            "r46h-remote-screen.sudoers\\nr46h-screenshot\\n"
            "r46h-screenshot-ssh\\nrollback.sh'"
        )
        self.assertIn(expected_payload, self.installer)
        for forbidden in (
            "/boot",
            "boot.ini",
            "/dev/disk",
            "saveenv",
            "mkfs",
            "dd if=",
            "curl ",
            "wget ",
        ):
            self.assertNotIn(forbidden, self.installer)
        self.assertNotIn("retroarch.cfg\\n", expected_payload)

    def test_rollback_removes_only_feature_files_and_preserves_frontend(self) -> None:
        for token in (
            'rm -f -- "$SUDOERS" "$CAPTURE" "$HELPER" "$GATEWAY" "$RECEIPT"',
            "Ozone config and frontend remained untouched",
            "frontend restarted during rollback",
            "RetroArch changed during rollback",
            "key_added",
        ):
            self.assertIn(token, self.rollback)
        for forbidden in (
            'rm -f -- "$CONFIG"',
            'rm -f -- "$RUNNER"',
            "systemctl stop r46h-gaming-frontend",
            "systemctl start r46h-gaming-frontend",
            "base-retroarch.cfg",
            "base-r46h-game-ui",
        ):
            self.assertNotIn(forbidden, self.rollback)

    def test_shell_and_python_entry_points_are_valid_and_executable(self) -> None:
        for name in (
            "build-drm-capture.sh",
            "install.sh",
            "rollback.sh",
            "r46h-screenshot",
            "r46h-screenshot-ssh",
        ):
            path = ROOT / name
            with self.subTest(name=name):
                self.assertEqual(
                    subprocess.run(["/bin/bash", "-n", str(path)], check=False).returncode,
                    0,
                )
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(FETCHER_PATH.stat().st_mode), 0o755)
        compile(self.fetcher_source, str(FETCHER_PATH), "exec")

    def test_fetcher_requires_public_key_and_preverified_host_key(self) -> None:
        for token in (
            '"BatchMode=yes"',
            '"IdentitiesOnly=yes"',
            '"PasswordAuthentication=no"',
            '"KbdInteractiveAuthentication=no"',
            '"StrictHostKeyChecking=yes"',
            '"HostKeyAlgorithms=ssh-ed25519"',
            '"UpdateHostKeys=no"',
            '"ClearAllForwardings=yes"',
            "known_hosts must contain exactly one non-comment entry",
            '"--read"',
            "checked_binary_to_file",
            "REMOTE_CLEANUP=",
        ):
            self.assertIn(token, self.fetcher_source)
        for forbidden in (
            "StrictHostKeyChecking=no",
            "sshpass",
            "PasswordAuthentication=yes",
            "ssh-keyscan",
            "scp",
            "rm -rf",
        ):
            self.assertNotIn(forbidden, self.fetcher_source)

    def test_marker_host_and_port_validation_fail_closed(self) -> None:
        digest = hashlib.sha256(PNG).hexdigest()
        marker = (
            "R46H_SCREENSHOT result=pass "
            f"name=r46h-screen-20260831T120000Z-123.png bytes={len(PNG)} sha256={digest}\n"
        )
        self.assertEqual(
            self.fetcher.parse_marker(marker),
            ("r46h-screen-20260831T120000Z-123.png", len(PNG), digest),
        )
        for rejected in (
            marker + "extra\n",
            marker.replace(".png", "../../escape.png"),
            marker.replace(f"bytes={len(PNG)}", "bytes=0"),
            marker.replace(digest, "bad"),
        ):
            with self.assertRaises(self.fetcher.FetchError):
                self.fetcher.parse_marker(rejected)
        self.assertEqual(self.fetcher.validate_host("192.168.1.42"), "192.168.1.42")
        for host in ("r46h.local", "192.168.001.42", "::1"):
            with self.assertRaises(self.fetcher.FetchError):
                self.fetcher.validate_host(host)
        for port in (0, 65536):
            with self.assertRaises(self.fetcher.FetchError):
                self.fetcher.validate_port(port)

    def test_png_structure_requires_ihdr_idat_iend_and_valid_crcs(self) -> None:
        self.fetcher.validate_png_structure(PNG)
        corrupted = bytearray(PNG)
        corrupted[-1] ^= 0x01
        with self.assertRaisesRegex(self.fetcher.FetchError, "CRC mismatch"):
            self.fetcher.validate_png_structure(bytes(corrupted))
        with self.assertRaises(self.fetcher.FetchError):
            self.fetcher.validate_png_structure(PNG[:8] + png_chunk(b"IEND", b""))
        wrong_size = (
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
            + png_chunk(b"IEND", b"")
        )
        with self.assertRaisesRegex(self.fetcher.FetchError, "fixed RGB output"):
            self.fetcher.validate_png_structure(wrong_size)
        wrong_filter = bytearray(PNG_RAW)
        wrong_filter[0] = 1
        filtered = (
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1024, 768, 8, 2, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(bytes(wrong_filter)))
            + png_chunk(b"IEND", b"")
        )
        with self.assertRaisesRegex(self.fetcher.FetchError, "row filter"):
            self.fetcher.validate_png_structure(filtered)

    def test_qt_png_profile_is_explicit_and_bounded(self) -> None:
        def image(color, filter_byte, raw_extra=b""):
            channels = 3 if color == 2 else 4
            return (b"\x89PNG\r\n\x1a\n"
                    + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, color, 0, 0, 0))
                    + png_chunk(b"IDAT", zlib.compress((bytes([filter_byte]) + bytes(2 * channels)) * 2 + raw_extra))
                    + png_chunk(b"IEND", b""))
        for color in (2, 6):
            for filter_byte in range(5):
                self.fetcher.validate_png_structure(image(color, filter_byte), profile="qt", width=2, height=2)
        with self.assertRaises(self.fetcher.FetchError):
            self.fetcher.validate_png_structure(image(6, 4))
        for data in (image(6, 5), image(6, 0, b"overflow")):
            with self.assertRaises(self.fetcher.FetchError):
                self.fetcher.validate_png_structure(data, profile="qt", width=2, height=2)
        with self.assertRaises(self.fetcher.FetchError):
            self.fetcher.validate_png_structure(image(6, 0), profile="qt", width=4096, height=4096)

    def test_known_hosts_must_be_one_exact_address_bound_ed25519_key(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="r46h-remote-screen-hostkey-test.", dir=requested_test_tmpdir()
        ) as directory:
            known_hosts = Path(directory) / "known_hosts"
            known_hosts.write_text(
                "192.168.1.42 ssh-ed25519 AAAATESTKEY\n", encoding="utf-8"
            )
            verified = subprocess.CompletedProcess([], 0, "# Host found\nssh-ed25519\n", "")
            with mock.patch.object(self.fetcher, "checked_capture", return_value=verified):
                self.fetcher.validate_known_hosts(known_hosts, "192.168.1.42", 22)
            known_hosts.write_text(
                "other ssh-ed25519 AAAATESTKEY\n", encoding="utf-8"
            )
            with self.assertRaises(self.fetcher.FetchError):
                self.fetcher.validate_known_hosts(known_hosts, "192.168.1.42", 22)

    def test_fetch_publishes_verified_png_before_exact_remote_cleanup(self) -> None:
        digest = hashlib.sha256(PNG).hexdigest()
        name = "r46h-screen-20260831T120000Z-123.png"
        marker = f"R46H_SCREENSHOT result=pass name={name} bytes={len(PNG)} sha256={digest}\n"
        cleanup = f"R46H_SCREENSHOT_REMOVE result=pass name={name}\n"
        events: list[str] = []

        def fake_capture(arguments: list[str], label: str):
            events.append(label)
            if label == "remote screenshot capture":
                return subprocess.CompletedProcess(arguments, 0, marker, "")
            if label == "remote screenshot cleanup":
                return subprocess.CompletedProcess(arguments, 0, cleanup, "")
            raise AssertionError(label)

        def fake_binary(arguments: list[str], destination: Path, label: str):
            events.append(label)
            self.assertIn("--read", arguments[-1])
            destination.write_bytes(PNG)

        with tempfile.TemporaryDirectory(
            prefix="r46h-remote-screen-fetch-test.", dir=requested_test_tmpdir()
        ) as directory:
            root = Path(directory)
            with (
                mock.patch.object(self.fetcher, "CACHE_ROOT", root / "cache"),
                mock.patch.object(self.fetcher, "OUTPUT_ROOT", root / "output"),
                mock.patch.object(self.fetcher, "checked_capture", side_effect=fake_capture),
                mock.patch.object(
                    self.fetcher, "checked_binary_to_file", side_effect=fake_binary
                ),
            ):
                final, cleanup_ok = self.fetcher.fetch(
                    "192.168.1.42", 22, root / "identity", root / "known_hosts"
                )
                self.assertTrue(cleanup_ok)
                self.assertEqual(final.name, name)
                self.assertEqual(final.read_bytes(), PNG)
                self.assertEqual(stat.S_IMODE(final.stat().st_mode), 0o600)
        self.assertEqual(
            events,
            ["remote screenshot capture", "screenshot download", "remote screenshot cleanup"],
        )


if __name__ == "__main__":
    unittest.main()
