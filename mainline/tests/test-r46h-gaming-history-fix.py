#!/usr/bin/env python3
"""Focused host tests for the R46H RetroArch history fix."""

from pathlib import Path
import hashlib
import re
import stat
import subprocess
import unittest


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "mainline/gaming-history-fix"
BASE_CONFIG = REPO / "mainline/gaming-rom-workflow/retroarch.cfg"


class GamingHistoryFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = (ROOT / "retroarch.cfg").read_text(encoding="utf-8")
        cls.base_config = BASE_CONFIG.read_text(encoding="utf-8")
        cls.installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        cls.rollback = (ROOT / "rollback.sh").read_text(encoding="utf-8")
        cls.readme = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_candidate_adds_only_the_runtime_verified_directory_keys(self) -> None:
        added = set(self.config.splitlines()) - set(self.base_config.splitlines())
        removed = set(self.base_config.splitlines()) - set(self.config.splitlines())
        self.assertEqual(
            added,
            {
                'content_favorites_directory = "/home/ark/.local/share/retroarch"',
                'content_history_directory = "/home/ark/.local/share/retroarch"',
                'content_image_history_directory = "/home/ark/.local/share/retroarch"',
                'content_music_history_directory = "/home/ark/.local/share/retroarch"',
                'content_video_directory = "/home/ark/.local/share/retroarch"',
            },
        )
        self.assertEqual(removed, set())
        self.assertNotIn("content_video_history_directory", self.config)

    def test_installer_pins_payload_base_and_transaction(self) -> None:
        config_sha256 = hashlib.sha256((ROOT / "retroarch.cfg").read_bytes()).hexdigest()
        rollback_sha256 = hashlib.sha256((ROOT / "rollback.sh").read_bytes()).hexdigest()
        for value in (
            "r46h-gaming-history-v0.2",
            "6.12.99-r46h-mainline-v0.10-adc-full-range",
            "c9f931c9-02",
            "621fdf049cd05e6aa02c62b5c42ed37a768ce9342af14c4563cfd4466d80d078",
            "08e0c35e924666b5fb946fadadad95218ed6d49d3e3eca3a8cee3f85d98700b4",
            "d33a1e23c83e2bbcfbb05180aabad4428d99809096f1ca589ddf1be308d2ff27",
            f"CONFIG_SHA256={config_sha256}",
            f"ROLLBACK_SHA256={rollback_sha256}",
            "unexpected payload member set",
            "systemctl stop r46h-gaming-frontend.service",
            "RetroArch process survived service stop",
            "BASE_RETROARCH_STATE_IDENTITY=0:0:755",
            "CANDIDATE_RETROARCH_STATE_IDENTITY=1000:1000:700",
            'chown 1000:1000 "$RETROARCH_STATE"',
            'chmod 0700 "$RETROARCH_STATE"',
            "retroarch_state_normalized=1",
            "base_retroarch_state_identity=%s",
            "retroarch_state_identity=%s",
            "mv -f -- \"$config_stage\" \"$CONFIG\"",
            "base-retroarch.cfg",
            "frontend remains stopped",
        ):
            self.assertIn(value, self.installer)
        self.assertNotIn("__CONFIG_SHA256__", self.installer)
        self.assertNotIn("__ROLLBACK_SHA256__", self.installer)

    def test_installer_is_p2_only_and_avoids_unrelated_surfaces(self) -> None:
        for forbidden in (
            "/boot",
            "boot.ini",
            "saveenv",
            "mkfs",
            "dd if=",
            "curl ",
            "wget ",
            "/roms/nes/r46h-nes-smoke.nes",
        ):
            self.assertNotIn(forbidden, self.installer)
        self.assertIn("EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count", self.installer)

    def test_rollback_is_exact_and_resumable(self) -> None:
        config_sha256 = hashlib.sha256((ROOT / "retroarch.cfg").read_bytes()).hexdigest()
        for value in (
            f"CONFIG_SHA256={config_sha256}",
            "current_config_sha256",
            '"$CONFIG_SHA256" || "$current_config_sha256" == "$BASE_CONFIG_SHA256"',
            "base-retroarch.cfg",
            "history receipt line count mismatch",
            "BASE_RETROARCH_STATE_IDENTITY=0:0:755",
            "CANDIDATE_RETROARCH_STATE_IDENTITY=1000:1000:700",
            "ROLLBACK_INTERMEDIATE_STATE_IDENTITY=1000:1000:755",
            'chmod 0755 "$RETROARCH_STATE"',
            'chown 0:0 "$RETROARCH_STATE"',
            "systemctl stop r46h-gaming-frontend.service",
            "exact v0.1 config",
        ):
            self.assertIn(value, self.rollback)
        self.assertNotIn("__CONFIG_SHA256__", self.rollback)
        self.assertIn('rollback_sha256=$(sha256sum "$STATE_DIR/rollback.sh"', self.rollback)
        self.assertIn('cmp -s "$STATE_DIR/rollback.sh" "$ROLLBACK"', self.rollback)
        self.assertIn('== 7 ]] || die \'history receipt line count mismatch\'', self.rollback)

    def test_installer_failure_restores_base_state_identity(self) -> None:
        cleanup = self.installer.split("cleanup_install() {", 1)[1].split(
            "[[ $# == 2", 1
        )[0]
        self.assertIn('chmod 0755 "$RETROARCH_STATE" || status=1', cleanup)
        self.assertIn('chown 0:0 "$RETROARCH_STATE" || status=1', cleanup)
        self.assertIn('"$BASE_RETROARCH_STATE_IDENTITY" ]] || status=1', cleanup)

    def test_shell_syntax_modes_and_documented_boundary(self) -> None:
        for name in ("install.sh", "rollback.sh"):
            path = ROOT / name
            subprocess.run(["/bin/bash", "-n", str(path)], check=True)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
        for phrase in (
            "PHYSICAL PASS / INSTALLED ON EXACT v0.10",
            "does not touch",
            "content_video_directory",
            "only after the v0.14 input",
            "stop the service from serial",
            "no controller hotkey for returning to RGUI",
            "state root to be `ark:ark 0700`",
            "reopened the same ROM from RGUI History",
            "seven-line receipt",
            "This proves history persistence",
        ):
            self.assertIn(phrase, self.readme)
        self.assertNotIn("return to RGUI and stop", self.readme)
        self.assertIsNone(re.search(r"(?i)charging|charge termination", self.readme))

    def test_installer_requires_explicit_hash_argument(self) -> None:
        result = subprocess.run(
            [str(ROOT / "install.sh")],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("--installer-sha256 HEX", result.stderr)


if __name__ == "__main__":
    unittest.main()
