#!/usr/bin/env python3
"""Focused host tests for the R46H ROM-over-Wi-Fi workflow."""

from pathlib import Path
import contextlib
import hashlib
import importlib.util
import io
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "mainline/gaming-rom-workflow"
UPLOADER = ROOT / "upload-rom.py"


def load_uploader_module():
    spec = importlib.util.spec_from_file_location("r46h_rom_uploader", UPLOADER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load ROM uploader module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def requested_test_tmpdir():
    requested = os.environ.get("R46H_TEST_TMPDIR")
    if requested:
        Path(requested).mkdir(parents=True, exist_ok=True)
    return requested


class GamingRomWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.uploader_source = UPLOADER.read_text(encoding="utf-8")
        cls.uploader = load_uploader_module()

    def test_config_uses_writable_user_state_and_rom_root(self) -> None:
        config = (ROOT / "retroarch.cfg").read_text(encoding="utf-8")
        required_paths = {
            "rgui_browser_directory": "/roms",
            "playlist_directory": "/home/ark/.local/share/retroarch/playlists",
            "content_history_path": "/home/ark/.local/share/retroarch/content_history.lpl",
            "content_favorites_path": "/home/ark/.local/share/retroarch/content_favorites.lpl",
            "content_music_history_path": "/home/ark/.local/share/retroarch/content_music_history.lpl",
            "content_video_history_path": "/home/ark/.local/share/retroarch/content_video_history.lpl",
            "content_image_history_path": "/home/ark/.local/share/retroarch/content_image_history.lpl",
            "savefile_directory": "/home/ark/.local/share/retroarch/saves",
            "savestate_directory": "/home/ark/.local/share/retroarch/states",
        }
        for name, path in required_paths.items():
            line = f'{name} = "{path}"'
            with self.subTest(name=name):
                self.assertEqual(config.count(line), 1)
        self.assertNotIn('content_history_path = "/etc/', config)
        self.assertEqual(config.count('config_save_on_exit = "false"'), 1)

    def test_installer_is_p2_only_fail_closed_and_no_clobber(self) -> None:
        script = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn("EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.10", script)
        self.assertIn("EXPECTED_ROOT_PARTUUID=c9f931c9-02", script)
        self.assertIn("BASE_RECEIPT_SHA256=08e0c35e", script)
        self.assertIn("BASE_CONFIG_SHA256=bdb46922", script)
        config_sha256 = hashlib.sha256((ROOT / "retroarch.cfg").read_bytes()).hexdigest()
        self.assertIn(f"CONFIG_SHA256={config_sha256}", script)
        self.assertNotIn("__CONFIG_SHA256__", script)
        self.assertIn("PAYLOAD_DIR=/run/r46h-rom-workflow-v0.1", script)
        self.assertIn("authorized_keys already contains different data", script)
        self.assertIn("installer SHA-256 mismatch", script)
        self.assertIn("public-key SHA-256 mismatch", script)
        self.assertIn("systemctl stop r46h-gaming-frontend.service", script)
        self.assertIn("RetroArch process survived service stop", script)
        self.assertIn("unexpected payload member set", script)
        self.assertIn("symbolic-link directory is forbidden", script)
        self.assertIn("/roms/$directory", script)
        self.assertIn("workflow_id=%s", script)
        self.assertIn('ln "$receipt_stage" "$RECEIPT"', script)
        self.assertLess(
            script.index("systemctl stop r46h-gaming-frontend.service"),
            script.index("install -d -o ark -g ark -m 0700 /home/ark/.ssh"),
        )
        for forbidden in (
            "/boot",
            "boot.ini",
            "saveenv",
            "mkfs",
            "dd if=",
            "curl ",
            "wget ",
            "PasswordAuthentication",
        ):
            self.assertNotIn(forbidden, script)

    def test_shell_syntax_and_runbook_boundary(self) -> None:
        self.assertEqual(
            subprocess.run(
                ["/bin/bash", "-n", str(ROOT / "install.sh")], check=False
            ).returncode,
            0,
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Historical/frozen contract", readme)
        self.assertIn("never committed", readme)
        self.assertIn("never as root", readme)
        self.assertIn("upload-rom.py", readme)
        self.assertIn("never overwrites an existing ROM", readme)
        self.assertIn("Compare the remote digest", readme)
        self.assertIn("does not scrape metadata", readme)
        self.assertIn("This is host evidence only", readme)
        self.assertIn("no board was powered on", readme)

    def test_uploader_is_executable_and_uses_pinned_public_key_transport(self) -> None:
        self.assertEqual(stat.S_IMODE(UPLOADER.stat().st_mode), 0o755)
        for token in (
            "SHA256:6C7YclGZi6qYujswYZD7yKb2SaWNsGA2bxeN3xTGjps",
            'SSH_KEYSCAN = "/usr/bin/ssh-keyscan"',
            'SSH_KEYGEN = "/usr/bin/ssh-keygen"',
            '"BatchMode=yes"',
            '"IdentitiesOnly=yes"',
            '"PasswordAuthentication=no"',
            '"KbdInteractiveAuthentication=no"',
            '"StrictHostKeyChecking=yes"',
            '"HostKeyAlgorithms=ssh-ed25519"',
            '"UpdateHostKeys=no"',
            'f"ark@{host}"',
            'prefix="r46h-rom-upload."',
        ):
            self.assertIn(token, self.uploader_source)
        for forbidden in (
            "StrictHostKeyChecking=no",
            "sshpass",
            "PasswordAuthentication=yes",
            "sudo ",
            "rm -rf",
            "/boot",
        ):
            self.assertNotIn(forbidden, self.uploader_source)

    def test_uploader_maps_only_supported_rom_extensions(self) -> None:
        for name, expected in (
            ("game.nes", "nes"),
            ("game.GB", "gb"),
            ("game.gbc", "gb"),
            ("game.GBA", "gba"),
            ("game.nds", "nds"),
        ):
            self.assertEqual(self.uploader.validate_rom_name(Path(name)), (name, expected))
        for name in ("game.zip", ".hidden.nes", "bad\nname.nes"):
            with self.assertRaises(self.uploader.UploadError):
                self.uploader.validate_rom_name(Path(name))

    def test_uploader_rejects_noncanonical_or_non_ipv4_hosts(self) -> None:
        self.assertEqual(self.uploader.validate_host("192.168.0.42"), "192.168.0.42")
        for host in ("r46h.local", "192.168.000.42", "::1", "192.168.0.256"):
            with self.assertRaises(self.uploader.UploadError):
                self.uploader.validate_host(host)
        for port in (0, 65536):
            with self.assertRaises(self.uploader.UploadError):
                self.uploader.validate_port(port)

    def test_remote_command_preserves_filename_argument_boundaries(self) -> None:
        command = self.uploader.remote_command(
            'printf "<%s>|<%s>\\n" "$1" "$2"',
            ["Game Name.nes", "quote'and space"],
        )
        result = subprocess.run(
            ["/bin/sh", "-c", command],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.stdout, "<Game Name.nes>|<quote'and space>\n")

    def test_local_private_key_and_rom_are_read_without_following_links(self) -> None:
        requested_root = requested_test_tmpdir()
        with tempfile.TemporaryDirectory(
            prefix="r46h-rom-uploader-test.", dir=requested_root
        ) as directory:
            root = Path(directory)
            key = root / "operator-key"
            key.write_text("test-private-key\n", encoding="utf-8")
            key.chmod(0o600)
            validated_key, _ = self.uploader.local_regular_file(
                key, "private key", private=True
            )
            self.assertEqual(validated_key, key.absolute())
            key.chmod(0o644)
            with self.assertRaises(self.uploader.UploadError):
                self.uploader.local_regular_file(key, "private key", private=True)

            rom = root / "Game's Test.NES"
            rom.write_bytes(b"deterministic-rom-fixture")
            validated = self.uploader.validate_rom(rom)
            self.assertEqual(validated[1:3], (rom.name, "nes"))
            self.assertEqual(validated[3], hashlib.sha256(rom.read_bytes()).hexdigest())
            link = root / "linked.nes"
            link.symlink_to(rom)
            with self.assertRaises(self.uploader.UploadError):
                self.uploader.validate_rom(link)

    def test_scanned_host_key_requires_the_serial_verified_fingerprint(self) -> None:
        requested_root = requested_test_tmpdir()
        with tempfile.TemporaryDirectory(
            prefix="r46h-rom-host-key-test.", dir=requested_root
        ) as directory:
            known_hosts = Path(directory) / "known_hosts"
            keyscan = subprocess.CompletedProcess(
                [], 0, "192.168.0.42 ssh-ed25519 AAAATESTKEY\n", ""
            )
            fingerprint = subprocess.CompletedProcess(
                [],
                0,
                "256 SHA256:6C7YclGZi6qYujswYZD7yKb2SaWNsGA2bxeN3xTGjps host (ED25519)\n",
                "",
            )
            binding = subprocess.CompletedProcess([], 0, "found\n", "")
            with mock.patch.object(
                self.uploader,
                "checked_capture",
                side_effect=(keyscan, fingerprint, binding),
            ):
                self.uploader.scan_pinned_host_key(
                    "192.168.0.42", 22, known_hosts
                )
            self.assertEqual(stat.S_IMODE(known_hosts.stat().st_mode), 0o600)
            self.assertEqual(
                known_hosts.read_text(encoding="utf-8"),
                "192.168.0.42 ssh-ed25519 AAAATESTKEY\n",
            )

            rejected = Path(directory) / "rejected_known_hosts"
            wrong = subprocess.CompletedProcess(
                [], 0, "256 SHA256:wrong host (ED25519)\n", ""
            )
            with mock.patch.object(
                self.uploader,
                "checked_capture",
                side_effect=(keyscan, wrong),
            ):
                with self.assertRaisesRegex(
                    self.uploader.UploadError, "fingerprint mismatch"
                ):
                    self.uploader.scan_pinned_host_key(
                        "192.168.0.42", 22, rejected
                    )

    def test_upload_success_uses_one_hidden_candidate_and_exact_markers(self) -> None:
        requested_root = requested_test_tmpdir()
        with tempfile.TemporaryDirectory(
            prefix="r46h-rom-upload-success-test.", dir=requested_root
        ) as directory:
            root = Path(directory)
            rom = root / "Game Name.nes"
            rom.write_bytes(b"upload-success-fixture")
            rom_path, name, system, digest, metadata = self.uploader.validate_rom(rom)
            preflight = subprocess.CompletedProcess(
                [], 0, "R46H_ROM_UPLOAD_PREFLIGHT result=pass\n", ""
            )
            marker = (
                f"R46H_ROM_UPLOAD result=pass system=nes "
                f"bytes={metadata.st_size} sha256={digest}\n"
            )
            published = subprocess.CompletedProcess([], 0, marker, "")
            copied = subprocess.CompletedProcess([], 0, "", "")
            output = io.StringIO()
            with (
                mock.patch.object(
                    self.uploader,
                    "run_remote",
                    side_effect=(preflight, published),
                ) as remote,
                mock.patch.object(
                    self.uploader.subprocess, "run", return_value=copied
                ) as process,
                contextlib.redirect_stdout(output),
            ):
                self.uploader.upload(
                    "192.168.0.42",
                    22,
                    root / "operator-key",
                    rom_path,
                    name,
                    system,
                    digest,
                    metadata,
                    root / "known_hosts",
                )
            self.assertEqual(remote.call_count, 2)
            preflight_arguments = remote.call_args_list[0].args[3]
            publish_arguments = remote.call_args_list[1].args[3]
            self.assertEqual(preflight_arguments[2], publish_arguments[2])
            self.assertRegex(
                preflight_arguments[2], r"^/roms/nes/\.r46h-upload-[0-9a-f]{32}$"
            )
            scp_arguments = process.call_args.args[0]
            self.assertEqual(scp_arguments[0], "/usr/bin/scp")
            self.assertEqual(
                scp_arguments[-1],
                f"ark@192.168.0.42:{preflight_arguments[2]}",
            )
            self.assertIn("PASS:", output.getvalue())
            self.assertIn(f"SHA256={digest}", output.getvalue())

            with (
                mock.patch.object(
                    self.uploader,
                    "run_remote",
                    side_effect=(
                        preflight,
                        self.uploader.UploadError("publish failed"),
                    ),
                ) as failed_remote,
                mock.patch.object(
                    self.uploader.subprocess, "run", return_value=copied
                ),
                mock.patch.object(
                    self.uploader, "cleanup_candidate", return_value=True
                ) as cleanup,
            ):
                with self.assertRaisesRegex(
                    self.uploader.UploadError, "publish failed"
                ):
                    self.uploader.upload(
                        "192.168.0.42",
                        22,
                        root / "operator-key",
                        rom_path,
                        name,
                        system,
                        digest,
                        metadata,
                        root / "known_hosts",
                    )
            failed_candidate = failed_remote.call_args_list[0].args[3][2]
            self.assertEqual(cleanup.call_args.args[3], failed_candidate)

    def test_remote_publish_is_hash_bound_atomic_and_no_clobber(self) -> None:
        for token in (
            '[[ ! -e "$final" && ! -L "$final" ]]',
            '[[ -f "$candidate" && ! -L "$candidate" ]]',
            "sha256sum \"$candidate\"",
            'ln -- "$candidate" "$final"',
            'rm -f -- "$candidate"',
            "rollback=1",
            'rm -f -- "$final"',
            "/sys/fs/ext4/mmcblk0p2/errors_count",
            "systemctl --failed --no-legend --plain",
            "R46H_ROM_UPLOAD result=pass",
        ):
            self.assertIn(token, self.uploader_source)
        self.assertNotIn('mv -f "$candidate" "$final"', self.uploader_source)
        self.assertEqual(
            self.uploader_source.count(
                "failed_units=$(systemctl --failed --no-legend --plain) || exit 1"
            ),
            3,
        )
        marker = self.uploader.PUBLISH_SCRIPT.index(
            "R46H_ROM_UPLOAD result=pass"
        )
        rollback_release = self.uploader.PUBLISH_SCRIPT.index(
            "rollback=0\ntrap - EXIT", marker
        )
        self.assertLess(marker, rollback_release)

    def test_embedded_remote_scripts_have_valid_bash_syntax(self) -> None:
        for script in (
            self.uploader.PRECHECK_SCRIPT,
            self.uploader.PUBLISH_SCRIPT,
            self.uploader.CLEANUP_SCRIPT,
        ):
            result = subprocess.run(
                ["/bin/bash", "-n"],
                input=script,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_uploader_help_and_argument_guard_do_not_touch_network(self) -> None:
        help_result = subprocess.run(
            [str(UPLOADER), "--help"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("Existing destination files are never replaced", help_result.stdout)
        missing = subprocess.run(
            [str(UPLOADER)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(missing.returncode, 2)
        self.assertEqual(missing.stdout, "")
        self.assertIn("--host HOST", missing.stderr)

    def test_installer_rejects_missing_authorization_arguments(self) -> None:
        result = subprocess.run(
            [str(ROOT / "install.sh")],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("--installer-sha256 HEX", result.stderr)


if __name__ == "__main__":
    unittest.main()
