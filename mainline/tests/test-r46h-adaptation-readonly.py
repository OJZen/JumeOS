#!/usr/bin/env python3
"""Static safety tests for the post-boot R46H adaptation audit."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import stat
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "mainline/bringup-tests/r46h-adaptation-readonly"
README = REPO_ROOT / "mainline/bringup-tests/ADAPTATION-READONLY.md"
ROOTFS = REPO_ROOT / "mainline/rootfs-debian13"
REGDB_HOTFIX = REPO_ROOT / "mainline/scripts/hotfix-debian13-v01-regdb.sh"


class R46HAdaptationReadonlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_shell_syntax_help_and_mode(self) -> None:
        subprocess.run(["/bin/bash", "-n", str(SCRIPT)], check=True)
        help_run = subprocess.run(
            ["/bin/bash", str(SCRIPT), "--help"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIn("non-mutating R46H Debian 13 adaptation audit", help_run.stdout)
        self.assertIn("--readonly", help_run.stdout)
        self.assertEqual(stat.S_IMODE(SCRIPT.stat().st_mode), 0o755)

    def test_exact_target_identity_is_pinned(self) -> None:
        for value in (
            "r46h-adaptation-readonly-v0.2",
            "6.12.99-r46h-mainline-v0.8-bootloader-handoff",
            "/dev/mmcblk0p2",
            "c9f931c9-02",
            "d3130001-46a4-4d56-9001-000000000001",
            "00E04C8188FF",
            "00:e0:4c:81:88:ff",
        ):
            self.assertIn(value, self.source)

    def test_runtime_writes_are_bounded_to_tmpfs(self) -> None:
        self.assertIn('findmnt -rn -T /run -o FSTYPE', self.source)
        self.assertIn('== tmpfs', self.source)
        self.assertIn("stat -c '%u:%a' -- /run", self.source)
        self.assertIn("mktemp -d /run/r46h-adaptation-supervisor.XXXXXX", self.source)
        self.assertIn('runtime_dir="$R46H_ADAPT_SESSION_DIR/worker"', self.source)
        self.assertIn('R46H_ADAPT_SESSION_INODE="$session_inode"', self.source)
        self.assertIn('mkdir -m 0700 -- "$LOCK_PATH"', self.source)
        self.assertIn('rmdir -- "$LOCK_PATH"', self.source)
        self.assertNotIn("/run/lock/", self.source)
        self.assertIn('"$path" == /run/r46h-adaptation-supervisor.*', self.source)
        self.assertIn('rm -rf -- "$path"', self.source)
        self.assertNotRegex(self.source, r"(?m)>\s*/(?:etc|boot|roms|sys|proc|var)/")
        self.assertNotRegex(self.source, r"(?m)\btee\s+/(?:etc|boot|roms|sys|proc|var)/")

    def test_no_mutating_hardware_commands(self) -> None:
        forbidden = (
            r"(?m)^\s*modetest\b.*(?:\s-[sPvrw]\b)",
            r"(?m)^\s*(?:sudo\s+)?(?:modprobe|rmmod|insmod)\b",
            r"(?m)^\s*(?:sudo\s+)?ip\s+link\s+set\b",
            r"(?m)^\s*(?:sudo\s+)?iw\b.*\bscan\b",
            r"(?m)^\s*(?:sudo\s+)?rfkill\s+(?:block|unblock|toggle)\b",
            r"(?m)^\s*(?:sudo\s+)?amixer\b.*\b(?:set|sset|cset)\b",
            r"(?m)^\s*(?:sudo\s+)?aplay\s+(?!-l\b)",
            r"(?m)^\s*(?:sudo\s+)?arecord\s+(?!-l\b)",
            r"(?m)\bcapture\s+[^\n]*\baplay\s+(?!-l\b)",
            r"(?m)\bcapture\s+[^\n]*\barecord\s+(?!-l\b)",
            r"(?m)^\s*(?:sudo\s+)?evtest\s+/dev/",
            r"(?m)^\s*(?:sudo\s+)?systemctl\s+(?:start|stop|restart|enable|disable)\b",
            r"(?m)^\s*(?:sudo\s+)?(?:dd|fbset|kmscube)\b",
        )
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, self.source))
        self.assertIn(
            'capture "$runtime_dir/modetest.txt" modetest -M rockchip -c -e -p',
            self.source,
        )
        self.assertIn('capture "$runtime_dir/aplay.txt" aplay -l', self.source)
        self.assertIn('capture "$runtime_dir/arecord.txt" arecord -l', self.source)
        self.assertIn(
            'capture "$runtime_dir/amixer.txt" amixer -c "$alsa_card" scontrols',
            self.source,
        )

    def test_all_adaptation_groups_have_required_checks(self) -> None:
        required_fragments = {
            "system": ("board-model", "compatible-r46h", "four-cpus"),
            "storage": ("root-partuuid", "p1-unmounted-anywhere", "ext4-errors-before"),
            "drm": ("rockchip-driver", "panfrost-render-driver", "modetest-query"),
            "input": ("joystick-abs", "gamepad-keys", "event-nodes"),
            "audio": ("playback-rk817", "mixer-master", "alsa-restore-masked"),
            "power": ("battery-voltage-plausible", "charger-online"),
            "thermal": ("plausible-zones", "soc-zone", "gpu-zone"),
            "performance": ("cpu-upstream-opps", "gpu-devfreq", "gpu-upstream-opps"),
            "media": ("media-node", "encoder-name", "decoder-name"),
            "wireless": ("usb-serial", "stable-mac", "rfkill-unblocked"),
            "kernel": ("post-audit", "full-boot-faults"),
        }
        for group, fragments in required_fragments.items():
            for fragment in fragments:
                with self.subTest(group=group, fragment=fragment):
                    self.assertIn(fragment, self.source)
        self.assertIn("dmesg_ring_wrapped", self.source)
        self.assertIn("fault_detected", self.source)
        self.assertIn("ext4_changed", self.source)
        self.assertIn(
            "for input_name in pwm-vibrator 'rk805 pwrkey' adc-joystick gpio-keys "
            "gpio-keys-vol 'rk817_int Headphones'; do",
            self.source,
        )
        self.assertIn('check input "device-${input_name// /-}"', self.source)
        self.assertIn("for module in rtl8xxxu rk817_charger hantro_vpu; do", self.source)
        self.assertIn('check modules "$module-vermagic"', self.source)
        self.assertIn('check modules "$module-loaded"', self.source)
        self.assertIn("check modules exfat-vermagic module_matches_release exfat", self.source)
        self.assertIn("skip modules exfat-loaded p3-unmounted", self.source)
        self.assertIn(
            "check storage p1-unmounted-anywhere source_unmounted_anywhere /dev/mmcblk0p1",
            self.source,
        )
        self.assertIn(
            "check storage p3-unmounted-anywhere source_unmounted_anywhere /dev/mmcblk0p3",
            self.source,
        )

    def test_rootfs_contains_every_external_diagnostic(self) -> None:
        packages: set[str] = set()
        for name in ("packages.base.txt", "packages.hardware.txt", "packages.graphics.txt"):
            packages.update(
                line
                for line in (ROOTFS / name).read_text(encoding="utf-8").splitlines()
                if line
            )
        self.assertTrue(
            {
                "alsa-utils",
                "evtest",
                "firmware-realtek",
                "iproute2",
                "iw",
                "kmod",
                "libdrm-tests",
                "lm-sensors",
                "procps",
                "rfkill",
                "usbutils",
                "util-linux",
            }.issubset(packages)
        )

    def test_result_is_fail_closed(self) -> None:
        self.assertIn("worker_complete == 1 && failures == 0 && status == 0", self.source)
        self.assertIn("R46H_ADAPT_WORKER_RESULT", self.source)
        self.assertIn("R46H_ADAPT_AUDIT id=%s mode=readonly result=%s", self.source)
        self.assertIn("skips=%d skip_names=%s cleanup=%s reason=%s", self.source)
        self.assertIn("worker_timeout=%ss output_timeout=%ss", self.source)
        self.assertIn('setsid timeout -s TERM -k 5 "$WORKER_TIMEOUT_SECONDS"', self.source)
        self.assertEqual(self.source.count("timeout -s TERM"), 1)
        self.assertIn('timeout --foreground -s TERM -k 2 "$COMMAND_TIMEOUT_SECONDS"', self.source)
        self.assertIn("readonly WORKER_TIMEOUT_SECONDS=160", self.source)
        self.assertIn("readonly OUTPUT_TIMEOUT_SECONDS=15", self.source)
        self.assertNotIn("SESSION_TIMEOUT_SECONDS", self.source)
        self.assertIn("forward_worker_signal()", self.source)
        self.assertIn('kill -"$signal_name" -- "-$worker_process"', self.source)
        self.assertIn('kill -"$signal_name" -- "$worker_process"', self.source)
        self.assertIn('kill -KILL -- "-$worker_pid"', self.source)
        self.assertIn("case $signal_status in", self.source)
        self.assertIn("supervisor_session_is_empty", self.source)
        self.assertIn("ps -eo sid=", self.source)
        self.assertIn("final_cleanup=fail", self.source)
        self.assertIn("supervisor-cleanup-failed", self.source)
        self.assertIn("trap '' INT TERM HUP", self.source)
        self.assertIn("ext4_changed == 0", self.source)
        self.assertIn("dmesg_ring_wrapped == 0", self.source)
        self.assertIn("fault_detected == 0", self.source)

    def test_skips_and_boot_faults_are_auditable(self) -> None:
        self.assertIn('skip_names+=("$1:$2")', self.source)
        self.assertIn(
            "none|audio:capture-enumeration|modules:exfat-loaded|"
            "audio:capture-enumeration,modules:exfat-loaded",
            self.source,
        )
        self.assertIn("worker_reason=unexpected-skip", self.source)
        self.assertIn("skip audio capture-enumeration not-release-gate", self.source)
        self.assertIn("skip modules exfat-loaded p3-unmounted", self.source)
        for marker in (
            "synchronous( external)? abort",
            "SError",
            "regulator|clk|clock|iommu",
            "drm|vop|dsi|mipi",
            "watchdog.*lockup",
            "rcu.*stall",
            "hung task",
        ):
            self.assertIn(marker, self.source)

    def test_fault_pattern_matches_failures_without_known_good_false_positives(self) -> None:
        pattern_parts = re.findall(
            r"(?m)^fault_pattern(?:\+)?='([^']*)'$",
            self.source,
        )
        self.assertGreaterEqual(len(pattern_parts), 10)
        pattern = "".join(pattern_parts)

        positive_samples = (
            "rockchip-iommu ff350800.iommu: Unhandled context fault",
            "INFO: task kworker/0:1:123 blocked for more than 120 seconds",
            "Internal error: synchronous external abort: 96000210",
            "SError Interrupt on CPU0",
            "panfrost ff300000.gpu: gpu mmu fault at 0x1000",
            "drm_sched_job_timedout: scheduler fence stalled",
            "mmc0: Timeout waiting for hardware interrupt",
            "EXT4-fs error (device mmcblk0p2): ext4_find_entry:1455",
            "dw-mipi-dsi ff450000.dsi: failed to transfer command",
            "vcc-sys: regulator failed to enable",
        )
        negative_samples = (
            "printk: debug: ignoring loglevel setting.",
            "rk817-charger rk817-charger: Invalid charge termination 52000, keeping default",
            "hantro-vpu ff360000.video-codec: Adding to iommu group 1",
            "iommu: Default domain type: Translated",
            "r46h-panel ff450000.dsi.0: bootloader handoff retained",
        )
        for sample in positive_samples:
            with self.subTest(sample=sample):
                result = subprocess.run(
                    ["grep", "-Eiq", pattern],
                    input=sample + "\n",
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0)
        for sample in negative_samples:
            with self.subTest(sample=sample):
                result = subprocess.run(
                    ["grep", "-Eiq", pattern],
                    input=sample + "\n",
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 1)

    def test_parsing_environment_is_fixed(self) -> None:
        self.assertIn("PATH=/usr/sbin:/usr/bin:/sbin:/bin", self.source)
        self.assertIn("LC_ALL=C", self.source)
        self.assertIn("LANG=C", self.source)
        self.assertIn("export PATH LC_ALL LANG", self.source)

    def test_runbooks_pin_the_script_and_order_active_tests(self) -> None:
        readme = README.read_text(encoding="utf-8")
        script_sha256 = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
        self.assertIn(script_sha256, readme)
        self.assertNotIn("SCRIPT_SHA256_TO_BE_FINALIZED", readme)
        self.assertIn("R46H_ADAPT_COMMAND_EXIT status=0", readme)
        self.assertIn("unset HISTFILE", readme)
        self.assertIn("set +o history", readme)
        self.assertIn("WRITE_COMPLETE", readme)
        self.assertIn("safe_to_boot=yes", readme)
        self.assertLess(
            readme.index("r46h-adaptation-readonly --readonly"),
            readme.index("r46h-rootfs-smoke --base"),
        )

        rootfs_readme = (ROOTFS / "README.md").read_text(encoding="utf-8")
        self.assertIn("hash-raw boot", rootfs_readme)
        self.assertIn("hash-raw root", rootfs_readme)
        self.assertIn(
            "6a4254a8e66c110405cf068317da5922bb5ddfe2a02535d1a381fe1303876c96",
            rootfs_readme,
        )
        self.assertIn("R46H_FIRSTBOOT_GATE result=pass status=0", rootfs_readme)
        self.assertIn(
            "firstboot_marker=$(sudo cat /var/lib/r46h/firstboot-complete",
            rootfs_readme,
        )
        self.assertLess(
            rootfs_readme.index("../bringup-tests/ADAPTATION-READONLY.md"),
            rootfs_readme.index("r46h-rootfs-smoke --base"),
        )

    def test_v01_regdb_hotfix_is_narrow_and_fail_closed(self) -> None:
        source = REGDB_HOTFIX.read_text(encoding="utf-8")
        rootfs_readme = (ROOTFS / "README.md").read_text(encoding="utf-8")
        subprocess.run(["/bin/bash", "-n", str(REGDB_HOTFIX)], check=True)
        self.assertEqual(stat.S_IMODE(REGDB_HOTFIX.stat().st_mode), 0o755)
        rejected = subprocess.run(
            ["/bin/bash", str(REGDB_HOTFIX), "--unexpected"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(rejected.returncode, 1)
        self.assertIn("result=fail reason=unexpected-arguments", rejected.stderr)
        hotfix_sha256 = hashlib.sha256(REGDB_HOTFIX.read_bytes()).hexdigest()
        self.assertIn(hotfix_sha256, rootfs_readme)
        self.assertIn("必须整体升为 v0.2", rootfs_readme)
        self.assertIn("regulatory.db.p7s-upstream", rootfs_readme)
        for value in (
            "debian13-p2-mvp-v0.1-regdb-upstream-v1",
            "release=debian13-p2-mvp-v0.1",
            "CONFIG_CFG80211_REQUIRE_SIGNED_REGDB=y",
            "CONFIG_CFG80211_USE_KERNEL_REGDB_KEYS=y",
            "c9f931c9-02",
            "d3130001-46a4-4d56-9001-000000000001",
            "2026.05.30-1~deb13u1",
            "2fb33ca0074db573e05ef7dd50bb45b63c0ff98b7e852e1105ebad536fae8e6b",
            "c941c08f51c93e46722293b85631604c3740d86c3de0c75f79aef50d2e919179",
            "update-alternatives --set regulatory.db",
            "/lib/firmware/regulatory.db.p7s-upstream",
            "reboot_required=yes",
        ):
            self.assertIn(value, source)
        for forbidden in ("apt-get", "modprobe", "rmmod", "systemctl reboot"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
