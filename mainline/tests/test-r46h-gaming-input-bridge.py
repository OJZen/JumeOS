#!/usr/bin/env python3
"""Focused host tests for the rollback-safe R46H gaming input bridge."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "mainline/gaming-input-bridge"
BUILDER_PATH = REPO / "mainline/scripts/build-r46h-gaming-input-bridge.py"
RUNBOOK = REPO / "mainline/bringup-tests/GAMING-INPUT-BRIDGE.md"
FRAGMENT = REPO / "mainline/config/r46h.fragment"
MANIFEST = REPO / "mainline/manifest.env"
BASE_CONFIG = REPO / "mainline/gaming-history-fix/retroarch.cfg"
BASE_RUNNER = REPO / "mainline/gaming-mvp/r46h-game-ui"


def load_builder():
    spec = importlib.util.spec_from_file_location("r46h_input_bridge", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load gaming input bridge builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_builder()


def config_values(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition(" = ")
        if separator != " = " or key in result:
            raise AssertionError(f"malformed or duplicate config line: {raw_line}")
        result[key] = value
    return result


class GamingInputBridgeTests(unittest.TestCase):
    def test_history_receipt_dependency_matches_installed_contract(self) -> None:
        receipt = "\n".join(
            (
                "fix_id=r46h-gaming-history-v0.2",
                "base_config_sha256=621fdf049cd05e6aa02c62b5c42ed37a768ce9342af14c4563cfd4466d80d078",
                "config_sha256=697aa82bb42689cd841f16a8ce1ae9c6ac2bdc56ccd1b811136f8f5884e600e9",
                "rollback_sha256=fb88d6f8d093527fb6b56730e6082cb088de97d8024ec1dac5f5b724acbc5819",
                "installer_sha256=066f2dd962cd6f34943e619c9dfa69a628c0e6680f61307d334aaab9ec64c49d",
                "base_retroarch_state_identity=0:0:755",
                "retroarch_state_identity=1000:1000:700",
                "",
            )
        ).encode()
        digest = hashlib.sha256(receipt).hexdigest()
        self.assertEqual(
            digest,
            "9b800245202992cbdc063e5cabd071a6265fbb9133e89a8718d0952209d0f1aa",
        )
        for name in ("install.sh", "remove.sh"):
            script = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(digest, script, name)

    def test_userspace_payload_identity_is_v05(self) -> None:
        self.assertEqual(MODULE.PAYLOAD_ID, "r46h-gaming-input-bridge-v0.5")
        expected = "r46h-gaming-input-bridge-v0.5"
        for name in ("install.sh", "remove.sh", "Dockerfile"):
            self.assertIn(expected, (ROOT / name).read_text(encoding="utf-8"), name)
        trial = (ROOT / "trial.sh").read_text(encoding="utf-8")
        self.assertIn("/var/lib/r46h-gaming-input-bridge/v0.5", trial)
        self.assertIn("gaming-input-bridge-v0.5-installed", trial)
        self.assertIn(
            '#define BRIDGE_VERSION "r46h-gaming-input-bridge-v0.5"',
            (ROOT / "r46h-input-bridge.c").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "/var/lib/r46h-gaming-input-bridge/v0.5/OPERATIONS.md",
            (ROOT / "r46h-input-bridge.service").read_text(encoding="utf-8"),
        )

    def test_product_kernel_retains_the_physically_proved_uinput_capability(self) -> None:
        fragment = FRAGMENT.read_text(encoding="utf-8")
        manifest = MANIFEST.read_text(encoding="utf-8")
        expected = "-r46h-mainline-v0.19-zram-product"
        self.assertEqual(fragment.count(f'CONFIG_LOCALVERSION="{expected}"'), 1)
        self.assertEqual(manifest.count(f"KERNEL_LOCALVERSION={expected}"), 1)
        self.assertEqual(manifest.count("KERNEL_PATCH_LAST=0008"), 1)
        self.assertEqual(fragment.count("CONFIG_INPUT_UINPUT=y"), 1)
        self.assertNotIn("# CONFIG_INPUT_UINPUT is not set", fragment)
        # The diagnostic builder remains frozen to the physically tested release.
        self.assertEqual(
            MODULE.TEST_RELEASE,
            "6.12.99-r46h-mainline-v0.14-gaming-input-bridge",
        )

    def test_bridge_discovers_exact_sources_and_mirrors_required_controls(self) -> None:
        source = (ROOT / "r46h-input-bridge.c").read_text(encoding="utf-8")
        for token in (
            'SYS_INPUT_ROOT "/sys/class/input"',
            'DEV_INPUT_ROOT "/dev/input"',
            '.name = "gpio-keys"',
            '.name = "adc-joystick"',
            'VIRTUAL_NAME "R46H Combined Gamepad"',
            "EVIOCGNAME",
            "EVIOCGBIT",
            "EVIOCGABS",
            "UI_DEV_SETUP",
            "UI_DEV_CREATE",
            "UI_DEV_DESTROY",
            "EVIOCGRAB, 1",
            "EVIOCGRAB, 0",
            "SYN_DROPPED",
            'DIAGNOSTICS_PATH "/run/r46h-input-bridge/diagnostics"',
            "source_presses",
            "emitted_presses",
            "source_samples",
            "emitted_samples",
            "uinput_write_failures",
            "failed_type",
            "failed_code",
            "failed_value",
            "O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW",
        ):
            self.assertIn(token, source)
        for key in (
            "BTN_SOUTH",
            "BTN_EAST",
            "BTN_NORTH",
            "BTN_WEST",
            "BTN_TL",
            "BTN_TR",
            "BTN_TL2",
            "BTN_TR2",
            "BTN_SELECT",
            "BTN_START",
            "BTN_DPAD_UP",
            "BTN_DPAD_DOWN",
            "BTN_DPAD_LEFT",
            "BTN_DPAD_RIGHT",
            "BTN_TRIGGER_HAPPY3",
            "BTN_TRIGGER_HAPPY4",
            "BTN_TRIGGER_HAPPY5",
        ):
            self.assertEqual(source.count(f"\t{key},"), 1)
        for axis in ("ABS_X", "ABS_Y", "ABS_RX", "ABS_RY"):
            self.assertEqual(source.count(f"\t{axis},"), 1)
        self.assertIn("minimum != 0", source)
        self.assertIn("maximum != 1023", source)
        self.assertIn("flat != 10", source)
        self.assertIn("fuzz != 10", source)
        self.assertNotIn('"/dev/input/event0"', source)
        self.assertNotIn("system(", source)
        self.assertIn("for (;;) {", source)
        self.assertNotIn("while ((entry = readdir(directory)) != NULL)", source)

    def test_candidate_config_changes_only_the_input_contract(self) -> None:
        base = config_values(BASE_CONFIG)
        candidate = config_values(ROOT / "retroarch.cfg")
        changed = {
            key
            for key in set(base) | set(candidate)
            if base.get(key) != candidate.get(key)
        }
        self.assertEqual(
            changed,
            {
                "input_player1_joypad_index",
                "input_player1_l_x_plus_axis",
                "input_player1_l_x_minus_axis",
                "input_player1_l_y_plus_axis",
                "input_player1_l_y_minus_axis",
                "input_player1_r_x_plus_axis",
                "input_player1_r_x_minus_axis",
                "input_player1_r_y_plus_axis",
                "input_player1_r_y_minus_axis",
                "input_player1_up_axis",
                "input_player1_down_axis",
                "input_player1_left_axis",
                "input_player1_right_axis",
                "input_player1_analog_dpad_mode",
            },
        )
        self.assertEqual(candidate["input_player1_joypad_index"], '"1"')
        self.assertEqual(candidate["input_player1_up_axis"], '"-1"')
        self.assertEqual(candidate["input_player1_down_axis"], '"+1"')
        self.assertEqual(candidate["input_player1_left_axis"], '"-0"')
        self.assertEqual(candidate["input_player1_right_axis"], '"+0"')
        self.assertEqual(candidate["input_player1_l_x_plus_axis"], '"+0"')
        self.assertEqual(candidate["input_player1_r_y_minus_axis"], '"-3"')
        self.assertEqual(candidate["input_player1_analog_dpad_mode"], '"0"')

    def test_service_is_static_bounded_and_hardened(self) -> None:
        unit = (ROOT / "r46h-input-bridge.service").read_text(encoding="utf-8")
        for setting in (
            "ExecStartPre=/usr/local/libexec/r46h-input-bridge --check",
            "ExecStart=/usr/local/libexec/r46h-input-bridge --diagnostics",
            "Restart=no",
            "TimeoutStopSec=5s",
            "RuntimeDirectory=r46h-input-bridge",
            "RuntimeDirectoryMode=0700",
            "RuntimeDirectoryPreserve=yes",
            "NoNewPrivileges=yes",
            "ProtectSystem=strict",
            "ProtectKernelModules=yes",
            "MemoryDenyWriteExecute=yes",
        ):
            self.assertIn(setting, unit)
        self.assertNotIn("[Install]", unit)
        self.assertNotIn("WantedBy=", unit)
        self.assertNotIn("ReadWritePaths=/run", unit)

    def test_install_is_inactive_boot_safe_and_bound_to_accepted_state(self) -> None:
        install = (ROOT / "install.sh").read_text(encoding="utf-8")
        for token in (
            "6.12.99-r46h-mainline-v0.10-adc-full-range",
            "08e0c35e924666b5fb946fadadad95218ed6d49d3e3eca3a8cee3f85d98700b4",
            "d33a1e23c83e2bbcfbb05180aabad4428d99809096f1ca589ddf1be308d2ff27",
            "9b800245202992cbdc063e5cabd071a6265fbb9133e89a8718d0952209d0f1aa",
            "697aa82bb42689cd841f16a8ce1ae9c6ac2bdc56ccd1b811136f8f5884e600e9",
            "history receipt mismatch",
            "RetroArch user state identity mismatch",
            "3d34e45ff35a6fa56e4b9d4fae3126dabdc60e1f6397d5419a25899b0f829708",
            "stat -c '%u:%g:%a' \"$PAYLOAD_DIR\"",
            "install.sh [--check-payload]",
            "payload contains a hard-linked file",
            "files/OPERATIONS.md",
            "'/run is not tmpfs'",
            'rm -f -- "$RECEIPT"',
            '[[ -d "$STATE_DIR" && ! -L "$STATE_DIR" ]]',
            "systemctl is-enabled r46h-input-bridge.service",
            "systemctl is-active r46h-input-bridge.service",
            "active frontend and BOOT are unchanged",
            "stale bridge diagnostics directory exists",
        ):
            self.assertIn(token, install)
        for forbidden in (
            "systemctl enable",
            "systemctl start",
            "systemctl restart",
            "systemctl stop r46h-gaming-frontend.service",
            "/boot/",
            "boot.ini",
            "saveenv",
            "mkfs",
            "dd if=",
            "curl ",
            "wget ",
        ):
            self.assertNotIn(forbidden, install)
        self.assertNotIn("stat -c '%u:%a:%h' \"$PAYLOAD_DIR\"", install)

    def test_trial_is_attended_bounded_and_captures_the_virtual_controller(self) -> None:
        trial = (ROOT / "trial.sh").read_text(encoding="utf-8")
        for token in (
            "6.12.99-r46h-mainline-v0.14-gaming-input-bridge",
            "[[ -t 0 && -t 1 && -t 2 ]]",
            'systemctl stop "$SERVICE"',
            'systemctl start "$SERVICE"',
            'systemctl is-active --quiet "$SERVICE"',
            '"$WAITER" --print-node',
            '/usr/bin/evtest "$virtual_node"',
            '"$RUNNER" smoke',
            "INPUT_WINDOW_SECONDS=60",
            "observed_span * 100 < advertised_span * 70",
            "return_delta * 100 <= advertised_span * 10",
            "presses == emitted_presses && releases == emitted_releases",
            "other == emitted_other && last == emitted_last",
            "source_span * 100 < advertised_span * 70",
            "source_min_delta * 100 > advertised_span * 20",
            "source_last_delta * 100 > advertised_span * 10",
            "SYN_DROPPED",
            "operator_screen_observation=required",
            "click the left stick cap (L3)",
            "click the right stick cap (R3)",
            'trap cleanup EXIT',
            '[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || status=1',
            '[[ -z "$(systemctl --failed --no-legend --plain)" ]] || status=1',
            "BRIDGE_KEY_AWK",
            "BRIDGE_AXIS_AWK",
            "BRIDGE_HEADER_AWK",
            "BRIDGE_SYN_AWK",
            "source_result=pass",
            "virtual-delivery-or-capture-missing",
            "physical-source-missing",
            "bridge-write-missing",
            "bridge diagnostics line count mismatch",
            "bridge diagnostics header reports a runtime failure",
            "R46H_INPUT_BRIDGE_RUNTIME result=fail",
            "DIAGNOSTICS_DIR=/run/r46h-input-bridge",
        ):
            self.assertIn(token, trial)
        for code in (
            "BTN_DPAD_UP",
            "BTN_DPAD_DOWN",
            "BTN_DPAD_LEFT",
            "BTN_DPAD_RIGHT",
            "BTN_EAST",
            "BTN_SOUTH",
            "BTN_WEST",
            "BTN_NORTH",
            "BTN_TL",
            "BTN_TR",
            "BTN_TL2",
            "BTN_TR2",
            "BTN_SELECT",
            "BTN_START",
            "BTN_TRIGGER_HAPPY3",
            "BTN_TRIGGER_HAPPY4",
            "BTN_TRIGGER_HAPPY5",
            "ABS_X",
            "ABS_Y",
            "ABS_RX",
            "ABS_RY",
        ):
            self.assertIn(code, trial)
        required_keys = re.search(
            r"(?ms)^readonly REQUIRED_KEYS=\(\n(.*?)^\)", trial
        )
        self.assertIsNotNone(required_keys)
        key_block = required_keys.group(1)  # type: ignore[union-attr]
        self.assertEqual(len(re.findall(r"\bBTN_[A-Z0-9_]+\b", key_block)), 16)
        self.assertNotIn("BTN_TRIGGER_HAPPY5", key_block)
        self.assertIn('/lib/modules/$EXPECTED_RELEASE', trial)
        self.assertNotIn("systemctl enable", trial)
        self.assertNotIn("saveenv", trial)
        self.assertNotIn('"$RUNNER" menu', trial)
        self.assertNotIn("nes-smoke", trial)

    def test_remover_validates_state_and_uses_only_exact_deletion(self) -> None:
        remove = (ROOT / "remove.sh").read_text(encoding="utf-8")
        self.assertIn("sha256sum -c SHA256SUMS", remove)
        self.assertIn("payload_id=r46h-gaming-input-bridge-v0.5", remove)
        self.assertIn("history receipt mismatch", remove)
        self.assertIn("RetroArch user state identity mismatch", remove)
        self.assertIn("candidate receipt line count mismatch", remove)
        self.assertIn("candidate state receipt mismatch", remove)
        self.assertIn("runtime_matches_or_absent", remove)
        self.assertIn("remove_runtime_diagnostics", remove)
        self.assertIn("unsafe bridge diagnostics directory", remove)
        self.assertIn("state_tombstone", remove)
        self.assertIn("restore_on_failure", remove)
        self.assertIn("deletion_started", remove)
        self.assertIn("unexpected candidate state member set", remove)
        self.assertNotIn("state_moved", remove)
        self.assertIn("rm -f --", remove)
        self.assertIn("rmdir --", remove)
        self.assertNotIn("rm -rf", remove)
        self.assertNotIn("/boot/", remove)
        self.assertNotIn("systemctl enable", remove)

    def test_builder_scope_runner_derivation_and_reproducible_archive(self) -> None:
        script = BUILDER_PATH.read_text(encoding="utf-8")
        for relative in MODULE.SOURCE_PATHS:
            self.assertIn(f'"{relative}"', script)
        self.assertIn("mainline/gaming-input-bridge/OPERATIONS.md", MODULE.SOURCE_PATHS)
        self.assertNotIn("mainline/bringup-tests/GAMING-INPUT-BRIDGE.md", MODULE.SOURCE_PATHS)
        self.assertIn('REPO / "mainline/out/.cache/r46h-gaming-input-bridge-build"', script)
        self.assertIn("source scope must be committed and clean", script)
        self.assertIn('"--network",\n            "none"', script)
        base = BASE_RUNNER.read_bytes()
        with self.assertRaisesRegex(
            MODULE.BuildError, "accepted gaming runner template identity mismatch"
        ):
            MODULE.render_candidate_runner(base)
        self.assertIn(
            b"6.12.99-r46h-mainline-v0.15-gaming-product", base
        )
        self.assertIn("run_extracted_archive_validation(docker, archive)", script)
        self.assertIn("test -x /run/{PAYLOAD_ID}/install.sh", script)
        self.assertIn("/run/{PAYLOAD_ID}/install.sh --check-payload", script)
        self.assertIn('"/run:rw,exec,nosuid,nodev,mode=755"', script)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = root / "payload"
            (payload / "files").mkdir(parents=True)
            (payload / "files/example").write_bytes(b"bridge\n")
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"
            MODULE.deterministic_archive(payload, first)
            MODULE.deterministic_archive(payload, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_scripts_are_syntactically_valid_and_runbook_keeps_proof_boundary(self) -> None:
        for name in ("install.sh", "remove.sh", "trial.sh", "r46h-input-bridge-wait"):
            self.assertEqual(
                subprocess.run(["/bin/bash", "-n", str(ROOT / name)], check=False).returncode,
                0,
                name,
            )
        runbook = " ".join(RUNBOOK.read_text(encoding="utf-8").split())
        self.assertIn("V0.1 PHYSICAL FAIL", runbook)
        self.assertIn("V0.2 TARGET-INCOMPATIBLE", runbook)
        self.assertIn("V0.3 PHYSICAL FAIL", runbook)
        self.assertIn("CLEANLY REMOVED", runbook)
        self.assertIn("This is host artifact proof only", runbook)
        self.assertIn("second review", runbook)
        self.assertIn("install.sh --check-payload", runbook)
        self.assertIn("does not replace either physical input driver", runbook)
        self.assertIn("does not", runbook)
        self.assertIn("active BOOT", runbook)
        self.assertIn("single bounded trial", runbook)
        self.assertIn("14/16 keys", runbook)
        self.assertIn("keys=4/16 axes=4/4 centered=3/4 failures=13", runbook)
        self.assertIn("Do not repeat unchanged v0.3", runbook)
        self.assertIn("V0.4 REJECTED BEFORE STAGING", runbook)
        self.assertIn("V0.5 COMPOSITE PHYSICAL PASS", runbook)
        self.assertIn("complete physical contract was therefore incomplete", runbook)
        self.assertIn("operator forgot L3/R3", runbook)
        self.assertIn("keys=14/16 axes=4/4 centered=4/4 failures=2", runbook)
        self.assertIn("no v0.1 through v0.5 archive authorizes an unchanged rerun", runbook)
        self.assertIn("physical-source-missing", runbook)
        self.assertIn("bridge-write-missing", runbook)
        self.assertIn("virtual-delivery-or-capture-missing", runbook)
        self.assertIn("This is host artifact proof only", runbook)
        self.assertIn("AArch64 bridge binary", runbook)
        self.assertIn("Do not transfer or stage the v0.4 archive", runbook)
        operations = (ROOT / "OPERATIONS.md").read_text(encoding="utf-8")
        self.assertIn("R46H_INPUT_BRIDGE_TRIAL result=machine-pass", operations)
        self.assertNotIn("final `result=pass`", operations)

    def _extract_awk_program(self, variable: str) -> str:
        source = (ROOT / "trial.sh").read_text(encoding="utf-8")
        match = re.search(
            rf"(?ms)^{variable}='\n(.*?)'\nreadonly {variable}$", source
        )
        self.assertIsNotNone(match)
        return match.group(1)  # type: ignore[union-attr]

    def test_trial_parsers_accept_complete_virtual_input_fixture(self) -> None:
        fixture = textwrap.dedent(
            """\
            Input device name: "R46H Combined Gamepad"
              Event code 0 (ABS_X)
                Value    510
                Min        0
                Max     1023
            Event: time 1.0, type 3 (EV_ABS), code 0 (ABS_X), value 20
            Event: time 1.1, type 3 (EV_ABS), code 0 (ABS_X), value 1000
            Event: time 1.2, type 3 (EV_ABS), code 0 (ABS_X), value 515
            Event: time 2.0, type 1 (EV_KEY), code 304 (BTN_SOUTH), value 1
            Event: time 2.1, type 1 (EV_KEY), code 304 (BTN_SOUTH), value 2
            Event: time 2.2, type 1 (EV_KEY), code 304 (BTN_SOUTH), value 0
            Event: time 2.3, type 1 (EV_KEY), code 304 (BTN_SOUTH), value 1
            Event: time 2.4, type 1 (EV_KEY), code 304 (BTN_SOUTH), value 0
            """
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.txt"
            path.write_text(fixture, encoding="utf-8")
            axis = subprocess.run(
                ["awk", "-v", "wanted=ABS_X", self._extract_awk_program("AXIS_AWK"), str(path)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
            key = subprocess.run(
                ["awk", "-v", "wanted=BTN_SOUTH", self._extract_awk_program("KEY_AWK"), str(path)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
            syn = subprocess.run(
                ["awk", self._extract_awk_program("SYN_AWK"), str(path)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
        self.assertEqual(axis.stdout.strip(), "0 1023 510 20 1000 515 3")
        self.assertEqual(key.stdout.strip(), "2 2 1 0")
        self.assertEqual(syn.stdout.strip(), "0")

    def test_trial_parsers_accept_exact_bridge_diagnostic_fixture(self) -> None:
        fixture = textwrap.dedent(
            """\
            R46H_INPUT_BRIDGE_DIAGNOSTIC kind=header version=r46h-gaming-input-bridge-v0.5 bridge_status=pass uinput_write_failures=0 failed_type=-1 failed_code=-1 failed_value=-1
            R46H_INPUT_BRIDGE_DIAGNOSTIC kind=key code=BTN_SOUTH source_presses=2 source_releases=2 source_other=0 source_last=0 emitted_presses=2 emitted_releases=2 emitted_other=0 emitted_last=0
            R46H_INPUT_BRIDGE_DIAGNOSTIC kind=axis code=ABS_X source_samples=9 source_min=10 source_max=1000 source_last=510 emitted_samples=9 emitted_last=510
            R46H_INPUT_BRIDGE_DIAGNOSTIC kind=syn source_reports=11 emitted_reports=11
            """
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostics.txt"
            path.write_text(fixture, encoding="utf-8")
            key = subprocess.run(
                [
                    "awk",
                    "-v",
                    "wanted=BTN_SOUTH",
                    self._extract_awk_program("BRIDGE_KEY_AWK"),
                    str(path),
                ],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
            axis = subprocess.run(
                [
                    "awk",
                    "-v",
                    "wanted=ABS_X",
                    self._extract_awk_program("BRIDGE_AXIS_AWK"),
                    str(path),
                ],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
            header = subprocess.run(
                ["awk", self._extract_awk_program("BRIDGE_HEADER_AWK"), str(path)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
            syn = subprocess.run(
                ["awk", self._extract_awk_program("BRIDGE_SYN_AWK"), str(path)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
        self.assertEqual(key.stdout.strip(), "2 2 0 0 2 2 0 0")
        self.assertEqual(axis.stdout.strip(), "9 10 1000 510 9 510")
        self.assertEqual(
            header.stdout.strip(),
            "r46h-gaming-input-bridge-v0.5 pass 0 -1 -1 -1",
        )
        self.assertEqual(syn.stdout.strip(), "11 11")


if __name__ == "__main__":
    unittest.main()
