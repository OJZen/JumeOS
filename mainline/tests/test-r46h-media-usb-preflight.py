#!/usr/bin/env python3
"""Static safety tests for the R46H media/USB active-test preflight."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import stat
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "mainline/bringup-tests/r46h-media-usb-preflight"
README = REPO_ROOT / "mainline/bringup-tests/MEDIA-USB-PREFLIGHT.md"
USB_READ_RUNBOOK = REPO_ROOT / "mainline/bringup-tests/USB-STORAGE-READ-PROBE.md"
EXPERIMENT_STATUS = REPO_ROOT / "mainline/board/r46h/EXPERIMENT-STATUS.md"


class R46HMediaUsbPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.readme = README.read_text(encoding="utf-8")
        cls.usb_read_runbook = USB_READ_RUNBOOK.read_text(encoding="utf-8")
        cls.ledger = EXPERIMENT_STATUS.read_text(encoding="utf-8")

    def test_shell_syntax_help_and_mode(self) -> None:
        subprocess.run(["/bin/bash", "-n", str(SCRIPT)], check=True)
        result = subprocess.run(
            ["/bin/bash", str(SCRIPT), "--help"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIn("Hantro/USB active-test preflight", result.stdout)
        self.assertIn("media=SKIP_TOOLING", result.stdout)
        self.assertIn("does not stream", result.stdout)
        self.assertEqual(stat.S_IMODE(SCRIPT.stat().st_mode), 0o755)

    def test_exact_target_identity_is_fail_closed(self) -> None:
        for value in (
            "r46h-media-usb-preflight-v0.1",
            "6.12.99-r46h-mainline-v0.8-bootloader-handoff",
            "/dev/mmcblk0p2",
            "c9f931c9-02",
            "d3130001-46a4-4d56-9001-000000000001",
            "GameConsole R46H",
            "rockchip,rk3326-r46h-linux",
            "00E04C8188FF",
            "0bda",
            "8179",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.source)
        self.assertIn("firstboot-marker", self.source)
        self.assertIn("firstboot-owner", self.source)
        self.assertIn("failed-units-before", self.source)
        self.assertIn("failed-units-after", self.source)
        self.assertIn("p1-unmounted", self.source)
        self.assertIn("p3-unmounted", self.source)

    def test_only_tmpfs_runtime_is_written(self) -> None:
        self.assertIn("REQUIRED_SCRIPT_PATH=/run/r46h-media-usb-preflight", self.source)
        self.assertIn("findmnt -rn -T /run -o FSTYPE", self.source)
        self.assertIn("== tmpfs", self.source)
        self.assertIn("stat -c '%u:%a' -- /run", self.source)
        self.assertIn(
            "mktemp -d /run/r46h-media-usb-preflight-supervisor.XXXXXX",
            self.source,
        )
        self.assertIn('runtime_dir="$R46H_MEDIA_USB_SESSION_DIR/worker"', self.source)
        self.assertIn('mkdir -m 0700 -- "$LOCK_PATH"', self.source)
        self.assertIn('rmdir -- "$LOCK_PATH"', self.source)
        self.assertNotRegex(
            self.source,
            r"(?m)>\s*/(?:boot|dev/(?!null(?:\s|$))|etc|home|media|mnt|proc|roms|sys|var)/",
        )
        self.assertNotRegex(
            self.source,
            r"(?m)\btee\s+/(?:boot|dev|etc|home|media|mnt|proc|roms|sys|var)/",
        )

    def test_no_media_usb_or_storage_mutation(self) -> None:
        forbidden = (
            r"(?m)^\s*(?:sudo\s+)?(?:dd|mount|umount|mkfs|fsck)\b",
            r"(?m)^\s*(?:sudo\s+)?(?:modprobe|rmmod|insmod)\b",
            r"(?m)^\s*(?:sudo\s+)?(?:eject|udisksctl)\b",
            r"(?m)^\s*(?:sudo\s+)?(?:ffmpeg|gst-launch-1\.0)\b",
            r"(?m)^\s*(?:sudo\s+)?v4l2-ctl\b.*(?:--stream|--set-|--overlay)",
            r"(?m)^\s*(?:sudo\s+)?(?:usbreset|hub-ctrl)\b",
            r"(?m)^\s*(?:sudo\s+)?(?:systemctl|service)\s+(?:start|stop|restart)",
            r"(?m)^\s*(?:sudo\s+)?(?:sh|bash)\s+-c\s+.*(?:authorized|bind|unbind)",
        )
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, self.source))
        self.assertIn("--all --list-formats-ext", self.source)
        self.assertNotIn("--stream-", self.source)
        self.assertNotIn("--set-fmt", self.source)
        self.assertNotIn("/sys/bus/usb/drivers_probe", self.source)
        self.assertNotIn("/authorized", self.source)
        self.assertNotIn("/bind", self.source)
        self.assertNotIn("/unbind", self.source)

    def test_media_nodes_are_discovered_by_sysfs_identity(self) -> None:
        self.assertIn("video_class_nodes=(/sys/class/video4linux/video*)", self.source)
        self.assertIn("media_device_nodes=(/dev/media*)", self.source)
        self.assertIn('readlink -f -- "/sys/dev/char/$media_dev"', self.source)
        self.assertIn("/sys/devices/platform/*.video-codec/media*", self.source)
        self.assertIn("*px30*vpu*enc*", self.source)
        self.assertIn("*px30*vpu*dec*", self.source)
        self.assertIn("${#encoder_nodes[@]} == 1", self.source)
        self.assertIn("${#decoder_nodes[@]} == 1", self.source)
        self.assertIn("${#media_nodes[@]} == 1", self.source)
        self.assertIn("exact-encoder-node", self.source)
        self.assertIn("exact-decoder-node", self.source)
        self.assertNotRegex(self.source, r"readonly\s+(?:ENCODER|DECODER)_NODE=/dev/video[01]")

    def test_missing_active_media_tooling_is_an_explicit_skip(self) -> None:
        for tool in ("v4l2-ctl", "ffmpeg", "gst-launch-1.0", "gst-inspect-1.0"):
            self.assertIn(f"command -v {tool}", self.source)
        self.assertIn("media_state=SKIP_TOOLING", self.source)
        self.assertIn("active-streaming-preflight SKIP_TOOLING", self.source)
        self.assertIn("media-tooling-unavailable", self.source)
        self.assertIn("result=skip", self.source)
        self.assertIn("final_status=77", self.source)
        self.assertIn("it is not evidence that Hantro data paths work", self.source)

    def test_usb_operation_is_inventory_only_and_stability_checked(self) -> None:
        self.assertIn("record_usb_inventory", self.source)
        self.assertIn("/sys/bus/usb/devices/*/idVendor", self.source)
        self.assertIn("R46H_USB_BASELINE sha256=", self.source)
        self.assertIn("builtin-wifi-identity", self.source)
        self.assertIn("inventory-stable", self.source)
        self.assertIn("mounts-unchanged", self.source)
        self.assertIn(
            'cmp -s "$runtime_dir/usb-before.txt" "$runtime_dir/usb-after.txt"',
            self.source,
        )
        self.assertIn(
            'cmp -s "$runtime_dir/mounts-before.txt" "$runtime_dir/mounts-after.txt"',
            self.source,
        )

    def test_each_external_probe_and_whole_worker_are_bounded(self) -> None:
        self.assertIn("readonly COMMAND_TIMEOUT_SECONDS=12", self.source)
        self.assertIn("readonly WORKER_TIMEOUT_SECONDS=90", self.source)
        self.assertIn('setsid timeout -s TERM -k 5 "$WORKER_TIMEOUT_SECONDS"', self.source)
        self.assertIn(
            'timeout --foreground -s TERM -k 2 "$COMMAND_TIMEOUT_SECONDS" "$@"',
            self.source,
        )
        self.assertIn("forward_worker_signal", self.source)
        self.assertIn("supervisor_session_is_empty", self.source)
        self.assertIn("case $signal_status in", self.source)
        self.assertIn('forward_worker_signal KILL "$worker_pid"', self.source)
        self.assertIn("worker-process-leak", self.source)
        self.assertIn("trap '' INT TERM HUP", self.source)
        self.assertIn("if (( worker_group_gone == 1 )); then", self.source)
        self.assertIn('if command -v "$command_name" >/dev/null 2>&1; then', self.source)
        self.assertNotIn('check preflight "command-$command_name" command -v', self.source)

    def test_post_checks_and_final_marker_are_structured(self) -> None:
        self.assertIn("/sys/fs/ext4/mmcblk0p2/errors_count", self.source)
        self.assertIn("dmesg-before.txt", self.source)
        self.assertIn("dmesg-after.txt", self.source)
        self.assertIn("dmesg_ring_wrapped", self.source)
        self.assertIn("fault_detected", self.source)
        self.assertIn("ext4_changed == 0", self.source)
        self.assertIn("R46H_MEDIA_USB_POST", self.source)
        self.assertIn("R46H_MEDIA_USB_WORKER_RESULT", self.source)
        self.assertIn("R46H_MEDIA_USB_GATE id=%s mode=query-only result=%s", self.source)
        self.assertIn("media=%s usb=%s post=%s cleanup=%s reason=%s", self.source)
        self.assertIn("findmnt -rn -o MAJ:MIN", self.source)
        self.assertNotIn('findmnt -rn -S "$1" -o TARGET', self.source)
        self.assertNotIn("check identity p1-unmounted source_unmounted_anywhere", self.source)
        self.assertNotIn("check identity p3-unmounted source_unmounted_anywhere", self.source)
        self.assertNotIn("check identity failed-units-before no_failed_units", self.source)
        self.assertNotIn("check identity failed-units-after no_failed_units", self.source)
        for sample in ("regulator", "clock", "iommu"):
            with self.subTest(sample=sample):
                self.assertIn(sample, self.source)

    def test_runbook_pins_hash_and_preserves_skip_boundary(self) -> None:
        script_hash = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
        self.assertEqual(self.readme.count(script_hash), 2)
        self.assertIn("R46H_MEDIA_USB_COMMAND_EXIT status=77", self.readme)
        self.assertIn("It is not evidence that the external USB Host", self.readme)
        self.assertIn("no codec capability or data path was validated", self.readme)

    def test_external_usb_read_receipt_is_pinned_and_bounded(self) -> None:
        for value in (
            "048d:1234",
            "4756901203712257914",
            "125,829,120,000",
            "first 128 MiB",
            "last 16 MiB",
            "iflag=direct,fullblock",
            "301,989,888",
            "8b8acf8c4c70f3c2b3d481c75423914083431e7e6ab79e13a99a4f5e7d22b73d",
            "dffab0dd410657cb30c7b2fd7f2586a4792e8472e58882b3532581f8111a646d",
            "ed7d91fdd2eb00761021d12718f137d33d2a9360affb2474405fd6b2c8f8f36f",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.usb_read_runbook)
        self.assertIn("did not mount it", self.usb_read_runbook)
        self.assertIn("issue any block-device write", self.usb_read_runbook)
        self.assertRegex(self.usb_read_runbook, r"not a\s+whole-device digest")
        self.assertIn("single external USB Host connector", self.usb_read_runbook)
        self.assertIn("USB-DC, not a second USB Host connector", self.usb_read_runbook)
        self.assertNotIn("either external USB host", self.readme)
        self.assertNotIn("The other physical connector,\nUSB writes", self.usb_read_runbook)
        self.assertIn("must not be relabelled", self.readme)

    def test_single_external_host_and_usb_dc_topology_is_pinned(self) -> None:
        for document in (self.usb_read_runbook, self.ledger):
            collapsed = " ".join(document.split())
            self.assertIn("single external USB Host", collapsed)
            self.assertIn("USB-DC", collapsed)
        for stale_claim in (
            "PASS (one port, read-only) / REST OPEN",
            "the other USB connector/write path",
            "The other connector, writes",
            "这不代表另一接口",
        ):
            with self.subTest(stale_claim=stale_claim):
                self.assertNotIn(stale_claim, self.usb_read_runbook)
                self.assertNotIn(stale_claim, self.ledger)


if __name__ == "__main__":
    unittest.main()
