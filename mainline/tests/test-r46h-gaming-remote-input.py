#!/usr/bin/env python3
"""Focused contracts for bounded ES-DE remote keyboard input."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
import unittest


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "mainline/gaming-remote-input"
OUTPUT = REPO / "mainline/out/r46h-gaming-remote-input-v0.1"
ACTIONS = (
    "up", "down", "left", "right", "a", "b", "x", "y",
    "select", "start", "l1", "r1", "l2", "r2", "l3", "r3",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RemoteInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (ROOT / "r46h-remote-input.c").read_text(encoding="utf-8")
        cls.gateway = (ROOT / "r46h-screenshot-ssh").read_text(encoding="utf-8")
        cls.sudoers = (ROOT / "r46h-remote-input.sudoers").read_text(encoding="utf-8")
        cls.builder = (ROOT / "build-payload.sh").read_text(encoding="utf-8")
        cls.installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        cls.rollback = (ROOT / "rollback.sh").read_text(encoding="utf-8")

    def test_helper_is_one_bounded_keyboard_pulse(self) -> None:
        self.assertIn('#define VERSION "r46h-gaming-remote-input-v0.1"', self.source)
        self.assertIn('#define DEVICE_NAME "R46H Remote Keyboard"', self.source)
        mapping = dict(re.findall(r'\{ "([a-z0-9]+)", (KEY_[A-Z0-9]+) \}', self.source))
        self.assertEqual(tuple(mapping), ACTIONS)
        self.assertEqual(
            mapping,
            {
                "up": "KEY_UP", "down": "KEY_DOWN", "left": "KEY_LEFT",
                "right": "KEY_RIGHT", "a": "KEY_ENTER", "b": "KEY_BACKSPACE",
                "x": "KEY_DELETE", "y": "KEY_INSERT", "select": "KEY_F1",
                "start": "KEY_ESC", "l1": "KEY_PAGEUP", "r1": "KEY_PAGEDOWN",
                "l2": "KEY_HOME", "r2": "KEY_END", "l3": "KEY_F2", "r3": "KEY_F3",
            },
        )
        for token in (
            "O_NOFOLLOW", "flock(fd, LOCK_EX | LOCK_NB)", "UI_DEV_SETUP",
            "UI_DEV_CREATE", "UI_DEV_DESTROY", "sleep_milliseconds(250)",
            "#define KEY_HOLD_MILLISECONDS 100",
            "sleep_milliseconds(KEY_HOLD_MILLISECONDS)",
            "find_action(\"up down\") == NULL",
        ):
            self.assertIn(token, self.source)
        for forbidden in ("socket(", "system(", "popen(", "execv("):
            self.assertNotIn(forbidden, self.source)

    def test_forced_key_preserves_screenshot_and_accepts_only_fixed_actions(self) -> None:
        for token in (
            '"$SCREENSHOT")', "--read|--remove", "SSH_ORIGINAL_COMMAND",
            "[[ -z \"${SSH_TTY-}\" ]]", "/usr/bin/sudo -n --",
            "^r46h-input[[:space:]]+",
        ):
            self.assertIn(token, self.gateway)
        match = re.search(
            r"\^r46h-input\[\[:space:\]\]\+\(([^)]+)\)\$", self.gateway
        )
        self.assertIsNotNone(match)
        self.assertEqual(tuple(match.group(1).split("|")), ACTIONS)
        self.assertNotIn("eval", self.gateway)

    def test_sudo_policy_lists_every_complete_command_without_wildcards(self) -> None:
        self.assertIn('/usr/local/libexec/r46h-drm-capture ""', self.sudoers)
        for action in ACTIONS:
            self.assertEqual(
                self.sudoers.count(f"/usr/local/libexec/r46h-remote-input {action}"), 1
            )
        self.assertNotIn("*", self.sudoers)

    def test_build_is_pinned_offline_and_rechecks_elf(self) -> None:
        self.assertIn(
            "BUILDER=sha256:3686fd20408cf746c1171e9345fd6c842a71f87e589f691b2455435b3bdd141a",
            self.builder,
        )
        self.assertIn(
            "EXPECTED_BINARY_SHA256=9907972995127792b75f0cf9922c3d750e8a06437b3d4d026f4a1db614f0232c",
            self.builder,
        )
        for token in (
            "--network none", "--pull never", "--read-only", "--self-test",
            "Machine:                           AArch64", "libc.so.6",
        ):
            self.assertIn(token, self.builder)
        self.assertNotIn("TO_BE_LOCKED", self.builder)

    def test_transaction_is_p2_only_no_restart_and_exactly_reversible(self) -> None:
        for text in (self.installer, self.rollback):
            for forbidden in (
                "/boot", "boot.ini", "/dev/disk", "mkfs", "saveenv",
                "systemctl stop r46h-gaming-frontend", "systemctl restart",
            ):
                self.assertNotIn(forbidden, text)
            for token in (
                "EXPECTED_ROOT_PARTUUID=c9f931c9-02",
                "EXPECTED_ROOT_UUID=d3130007-46a4-4d56-9001-000000000007",
                "REMOTE_SCREEN_RECEIPT_SHA256=28aae35ba2f35255ae628949b76f1bb1d271be887cd51a81f12d73c0bd771957",
                "REMOTE_SCREEN_ES_DE_RECEIPT_SHA256=caa07dbac59572217b8faca95ba5ddc8b7ea50a93b92e726f64916f809b8aa39",
                "OLD_GATEWAY_SHA256=5932dd1eec9c510cf9f4a8c5f0425c7b4afa083c473d290e57c9775f15b6a638",
                "OLD_SUDOERS_SHA256=f366b8815b00f477521ef6d42e4dc2c94d3997e77940b66cacfc8548911e1ed6",
                "INPUT_SHA256=9907972995127792b75f0cf9922c3d750e8a06437b3d4d026f4a1db614f0232c",
                "active_frontend_pid", "frontend_restarts", "findmnt -rn -o OPTIONS /roms",
            ):
                self.assertIn(token, text)
            self.assertNotIn("TO_BE_LOCKED", text)
        self.assertIn(f"ROLLBACK_SHA256={sha256(ROOT / 'rollback.sh')}", self.installer)
        self.assertIn('previous-gateway" "$GATEWAY"', self.installer)
        self.assertIn('previous-sudoers" "$SUDOERS"', self.installer)
        self.assertIn('previous-gateway" "$gateway_stage"', self.rollback)
        self.assertIn('previous-sudoers" "$sudoers_stage"', self.rollback)
        self.assertIn("/usr/sbin/visudo -cf", self.installer)
        self.assertIn("/usr/sbin/visudo -cf", self.rollback)

    def test_scripts_parse_and_payload_matches(self) -> None:
        for path in (
            ROOT / "build-payload.sh", ROOT / "install.sh", ROOT / "rollback.sh",
            ROOT / "r46h-screenshot-ssh",
        ):
            subprocess.run(["bash", "-n", str(path)], check=True)
        if not OUTPUT.exists():
            self.skipTest("payload is not assembled")
        expected = {
            "README.md", "SHA256SUMS", "install.sh", "r46h-remote-input",
            "r46h-remote-input.sudoers", "r46h-screenshot-ssh", "rollback.sh",
        }
        self.assertEqual({path.name for path in OUTPUT.iterdir()}, expected)
        entries = {}
        for line in (OUTPUT / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            digest, name = line.split("  ", 1)
            entries[name] = digest
        self.assertEqual(set(entries), expected - {"SHA256SUMS"})
        for name, digest in entries.items():
            self.assertEqual(sha256(OUTPUT / name), digest)


if __name__ == "__main__":
    unittest.main()
