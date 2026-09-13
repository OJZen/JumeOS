#!/usr/bin/env python3
"""Safety and artifact checks for the R46H factory-kernel jack control."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "mainline/bringup-tests/r46h-audio-jack-vendor-control.c"
RUNBOOK = REPO / "mainline/bringup-tests/AUDIO-JACK-VENDOR-CONTROL.md"
BATCH = REPO / "mainline/bringup-tests/ATTENDED-INPUT-AUDIO-COMPLETION.md"
SOURCE_SHA256 = "8684cd88355b1012b8c993fb55b47d6fc0ec5c126389d24fcde1e4878ad311d2"
SOURCE_COMMIT = "c360b632b77d0ed785dc6895a5bbf399447bca49"
BUILDER_IMAGE_ID = "sha256:6b4a05209b13e72ae2ae02056f14fe75d79b4ba8b8b0f6d403559c0e6921158c"
V01_SOURCE_SHA256 = "629d59e7e79c90681d380e1a727ddbaa5bad4737d819e6985b8b6153f971cd3a"
V01_BINARY_SHA256 = "6b0c654b68c154e44ee372388a99a88efadbe82fbb403c6f038e7432183fbfbe"
V01_CPIO_SHA256 = "5c7b7c6202d0652f6e222b0b5f1c0edd87a687c4ff84a3a831b97cd7ad638562"
V01_LZ4_SHA256 = "04d40cb81cf34048cb4f3be91e80ccbc72ba6d84edc4704a33be89d8eee81e34"
V01_UINITRD_SHA256 = "32f4f0ec8c5924cf31b3743a0f316950050caa38c3c4e41763a4eecd73650f1e"
BINARY_SHA256 = "2be2a1909319c8276db9876f13b5fef47e628ae333ec5962d1f304a0ad337057"
CPIO_SHA256 = "4259f91bcf6ab2d4db3d1449b9a94a372f6d2422443b3c08406d5a8d90022489"
LZ4_SHA256 = "9e4da0bcded50ed29313b9630af9c044da234e332b20d576aa0ebe67befc360e"
UINITRD_SHA256 = "b6403a97c0e465bd2f977d5ac557c0dc28ab6cb27b01424b843a7605b0bb67ff"
STAGING_SERIAL_SHA256 = "33722e159593409beb1774a6dc2aae0614a34eab96581cd3c49e3be9b79ad0ab"
FACTORY_SERIAL_SHA256 = "445a5a3d68315a13cb59c4a6fed456b44fefa9eeeca6d7e78260181993076c22"
CLEANUP_SERIAL_SHA256 = "b26ac35b8eb3ea2ecfde4e644763e3ea154b0bf000734b40638bab77a8d96427"


class R46HAudioJackVendorControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")
        cls.batch = BATCH.read_text(encoding="utf-8")

    def test_source_identity_mode_and_artifact_pins(self) -> None:
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), SOURCE_SHA256)
        self.assertEqual(stat.S_IMODE(SOURCE.stat().st_mode), 0o644)
        for digest in (
            SOURCE_SHA256,
            SOURCE_COMMIT,
            BUILDER_IMAGE_ID,
            V01_SOURCE_SHA256,
            V01_BINARY_SHA256,
            V01_CPIO_SHA256,
            V01_LZ4_SHA256,
            V01_UINITRD_SHA256,
            BINARY_SHA256,
            CPIO_SHA256,
            LZ4_SHA256,
            UINITRD_SHA256,
            STAGING_SERIAL_SHA256,
            FACTORY_SERIAL_SHA256,
            CLEANUP_SERIAL_SHA256,
        ):
            self.assertIn(digest, self.runbook)
        self.assertIn(V01_UINITRD_SHA256, self.batch)
        self.assertNotIn(UINITRD_SHA256, self.batch)
        for size in (
            "708,488",
            "709,632",
            "352,953",
            "353,017",
            "708,456",
            "351,956",
            "352,020",
        ):
            self.assertIn(size, self.runbook)

    def test_exact_vendor_runtime_and_gpio_identity_are_required(self) -> None:
        for token in (
            'PROBE_ID "r46h-audio-jack-vendor-control-v0.2"',
            'EXPECTED_RELEASE "4.4.189"',
            'EXPECTED_MODEL "GameConsole R46H"',
            'EXPECTED_EXECUTABLE "/init"',
            '"/sys/firmware/devicetree/base/model"',
            'GPIO_DEBUG_PATH "/sys/kernel/debug/gpio"',
            'GPIO_LINE_NAME "Headphone detection"',
            'GPIO_NUMBER_TEXT "gpio-86"',
            "has_exact_gpio_number",
            "parse_gpio_line",
            "*has_irq = false",
            "*has_irq = true",
            'path_metadata.st_nlink != 1',
            '(path_metadata.st_mode & 07777) != 0700',
            'stat("/proc/self/exe", &self_metadata)',
            "self_metadata.st_ino != path_metadata.st_ino",
            'open("/dev/console"',
            "O_RDWR | O_NOCTTY | O_CLOEXEC | O_NOFOLLOW",
            "!S_ISCHR(console_metadata.st_mode)",
            "major(console_metadata.st_rdev) != 5",
            "minor(console_metadata.st_rdev) != 1",
            "dup2(console_fd, STDIN_FILENO)",
            "dup2(console_fd, STDOUT_FILENO)",
            "dup2(console_fd, STDERR_FILENO)",
            "!isatty(STDIN_FILENO)",
        ):
            self.assertIn(token, self.source)
        self.assertNotIn("has_irq_suffix", self.source)
        self.assertNotIn("IRQ ACTIVE LOW", self.source)

    def test_probe_never_requests_gpio_or_touches_audio_or_storage(self) -> None:
        for forbidden in (
            "EVIOCGRAB",
            "GPIO_GET_LINEHANDLE_IOCTL",
            "gpiod_",
            "/sys/class/gpio/export",
            "pinctrl-select",
            "amixer",
            "speaker-test",
            "alsactl",
            "O_WRONLY",
            "O_CREAT",
            "/dev/mmc",
            '"ext4"',
            '"vfat"',
            "fork(",
            "execl(",
            "execv(",
            "execve(",
            "system(",
        ):
            self.assertNotIn(forbidden, self.source)
        self.assertIn("O_RDONLY | O_CLOEXEC | O_NOFOLLOW", self.source)
        self.assertEqual(self.source.count("O_RDWR"), 1)

    def test_initramfs_pid1_mounts_only_pseudo_filesystems_and_powers_off(self) -> None:
        for token in (
            "getpid() != 1",
            'mount("devtmpfs", "/dev", "devtmpfs"',
            'mount("proc", "/proc", "proc"',
            'mount("sysfs", "/sys", "sysfs"',
            'mount("debugfs", "/sys/kernel/debug", "debugfs"',
            "MS_RDONLY | MS_NOSUID | MS_NODEV | MS_NOEXEC",
            'umount2("/sys/kernel/debug", MNT_DETACH)',
            'umount2("/sys", MNT_DETACH)',
            'umount2("/proc", MNT_DETACH)',
            'umount2("/dev", MNT_DETACH)',
            "persistent_storage_mounted=no normal_userspace_started=no",
            "reboot(RB_POWER_OFF)",
            "for (;;)\n\t\tpause();",
        ):
            self.assertIn(token, self.source)
        self.assertEqual(self.source.count("mount("), 4)
        self.assertEqual(self.source.count("umount2("), 4)
        self.assertEqual(self.source.count("MS_RDONLY"), 3)

    def test_observation_is_bounded_and_fail_closed(self) -> None:
        for token in (
            "OBSERVE_SECONDS 30",
            "GPIO_SAMPLE_MILLISECONDS 20",
            "headphones-must-start-removed",
            "headphones-not-removed",
            "operator-signal",
            "vendor-gpio-cycle-observed",
            "mainline-specific-path-suspect",
            "vendor-gpio-transitions-missing",
            "shared-electrical-socket-or-common-pin-state",
            "R46H_AUDIO_JACK_VENDOR_CONTROL id=%s kernel=%s result=%s",
            'const char *release = "unavailable"',
            "PROBE_ID, release, result, reason, localization",
            "R46H_AUDIO_JACK_VENDOR_CONTROL_COMMAND status=%d",
            "R46H_AUDIO_JACK_VENDOR_CONTROL_POWEROFF status=%d",
            "R46H_AUDIO_JACK_VENDOR_CONTROL_GPIO_READ phase=%s",
            "R46H_AUDIO_JACK_VENDOR_CONTROL_GPIO_LINE gpio=%s",
            'emit_gpio_read_error("initial", failure_stage)',
            'emit_gpio_read_error("sample", failure_stage)',
            'emit_gpio_read_error("final", failure_stage)',
            "gpio-line-identity-changed",
        ):
            self.assertIn(token, self.source)
        self.assertEqual(self.source.count('*result = "pass";'), 1)
        self.assertIn('*result = "fail";', self.source)

    def test_runbook_freezes_factory_files_and_one_shot_boot(self) -> None:
        collapsed = " ".join((self.runbook + " " + self.batch).split())
        for token in (
            "eda795942083d198d7223dcf3f65e19c05c4c7bfc754935e4f84d3a0cc15bbfd",
            "ff42fbf07d9455b483f2e21eef074a7b2bcb13eb3ca2cba7c40b1193d6c79af8",
            "c9f931c9-01",
            "c9f931c9-02",
            "0xc7d808",
            "0x16e02",
            "0x562f9",
            "0x01100040:0x000562b9",
            "iminfo ${initrd_loadaddr}",
            "rdinit=/init",
            "CONFIG_RD_LZ4",
            "02 21 4c 18",
            "/opt/homebrew/bin/lz4 -q -f -l -12 -T1",
            "mkimage -A arm -O linux -T ramdisk -C gzip",
            "Never use `saveenv`",
            "current-media identity",
            "no block filesystem is mounted by PID 1",
            "stage=$(mktemp -d /tmp/r46h-audio-jack-vendor-control-v0.2.XXXXXX)",
            'install -m 0700 /work/r46h-audio-jack-vendor-control "$stage/init"',
            "Container-local staging preserves the reviewed root-owned mode-`0700` `/init`",
            "R46H vendor jack control v0.2",
            "audio-jack-vendor-control-v0.2/uInitrd",
        ):
            self.assertIn(token, collapsed)
        self.assertNotIn("booti ${loadaddr} ${initrd_loadaddr}", self.runbook)
        self.assertNotIn("rootfs/init", self.runbook)
        self.assertNotIn("audio-jack-vendor-control-v0.1/uInitrd", self.runbook)

    def test_one_shot_load_ranges_are_disjoint_and_header_is_exact(self) -> None:
        initrd_start = 0x01100000
        initrd_size = 353_017
        payload_size = 352_953
        dtb_start = 0x01F00000
        dtb_size = 93_698
        image_start = 0x02000000
        image_size = 13_096_968
        self.assertEqual(initrd_size, 0x562F9)
        self.assertEqual(payload_size, 0x562B9)
        self.assertEqual(initrd_size, 64 + payload_size)
        self.assertLessEqual(initrd_start + initrd_size, dtb_start)
        self.assertLessEqual(dtb_start + dtb_size, image_start)
        self.assertLess(image_start + image_size, 0x03000000)

    def test_runbook_preserves_interpretation_and_cleanup_boundaries(self) -> None:
        collapsed = " ".join((self.runbook + " " + self.batch).split())
        for phrase in (
            "does not request or drive a GPIO",
            "This is a control experiment, not a fix",
            "cannot by itself prove a damaged socket",
            "mainline-specific pinctrl/GPIO/ASoC path",
            "shared electrical/socket/plug or common pin-state boundary",
            "does not authorize headphone playback",
            "Do not repeat the unchanged v0.10 localizer",
            "Do not repeat this unchanged control",
            "remove only the staged files and their empty directories",
            "No TF-card rewrite",
        ):
            self.assertIn(phrase, collapsed)
        self.assertIn("V0.1 PHYSICAL INFRASTRUCTURE FAIL", collapsed)
        self.assertIn("V0.2 CONCLUSIVE PHYSICAL NO-TRANSITION", collapsed)
        self.assertIn("GPIO CONTROL CLOSED", collapsed)
        self.assertIn("PHYSICAL OUTPUT LATER PASSED SEPARATELY", collapsed)
        self.assertIn("AUTOMATIC DAPM MUTING UNTESTED", collapsed)
        self.assertIn(
            "does not test headphone output or automatic speaker muting", collapsed
        )
        self.assertIn("reason=initial-gpio-state-unreadable", collapsed)
        self.assertIn("No headset action occurred", collapsed)
        self.assertIn("reason=vendor-gpio-transitions-missing", collapsed)
        self.assertIn("localization=shared-electrical-socket-or-common-pin-state", collapsed)
        self.assertIn("irq=absent", collapsed)
        self.assertIn("samples=1463", collapsed)
        self.assertIn("Do not repeat this unchanged v0.2 control", collapsed)
        self.assertIn("Frozen inactive p2 staging procedure", collapsed)
        self.assertIn("Frozen factory-kernel one-shot", collapsed)
        self.assertIn("Frozen exact cleanup", collapsed)
        self.assertNotIn("PHYSICAL PENDING", self.runbook)
        self.assertNotIn("No target staging or physical v0.2 run has occurred", self.runbook)
        self.assertIn(
            "test \"$(sudo stat -c '%u:%g:%a:%h'",
            self.runbook,
        )
        self.assertIn(
            "test ! -L /home/ark/.cache/r46h-audio-jack-vendor-control-v0.2/uInitrd",
            self.runbook,
        )
        self.assertIn('"$(id -u):$(id -g):600:1"', self.runbook)
        self.assertNotIn("sudo test \"$(stat -c", self.runbook)
        self.assertNotIn("rm -rf", self.runbook)

    def test_v02_accepts_only_optional_irq_on_the_exact_input_line(self) -> None:
        for token in (
            "low_without_irq",
            "wrong_line",
            "output_line",
            "extra_token_line",
            "duplicate_lines",
            'has_irq ? "present" : "absent"',
            "has_irq != initial_has_irq",
        ):
            self.assertIn(token, self.source)
        collapsed = " ".join(self.runbook.split())
        for phrase in (
            "unique consumer, `gpio-86`, input direction, high/low grammar",
            "may end either with `IRQ` or whitespace",
            "An extra suffix token, output direction, wrong number",
            "used for the single physical control recorded next",
            "The changed control ran exactly once",
            "All 1,463 valid samples remained raw high",
            "GPIO_READ phase=initial stage=... result=fail errno=...",
        ):
            self.assertIn(phrase, collapsed)

    @unittest.skipUnless(
        sys.platform.startswith("linux") and shutil.which("cc") is not None,
        "Linux mount/reboot headers and a native C compiler are required",
    )
    def test_linux_build_selftest_help_and_no_argument_guard(self) -> None:
        requested_root = os.environ.get("R46H_TEST_TMPDIR")
        if requested_root:
            temporary_parent = Path(requested_root)
            temporary_parent.mkdir(parents=True, exist_ok=True)
            directory_context = tempfile.TemporaryDirectory(
                prefix="r46h-audio-jack-vendor-control-test.", dir=temporary_parent
            )
        else:
            directory_context = tempfile.TemporaryDirectory(
                prefix="r46h-audio-jack-vendor-control-test."
            )
        with directory_context as directory:
            binary = Path(directory) / "r46h-audio-jack-vendor-control"
            subprocess.run(
                [
                    "cc",
                    "-std=c11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-o",
                    str(binary),
                    str(SOURCE),
                ],
                check=True,
            )
            selftest = subprocess.run(
                [str(binary), "--self-test"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertIn(
                "R46H_AUDIO_JACK_VENDOR_CONTROL_SELFTEST result=pass",
                selftest.stdout,
            )
            help_run = subprocess.run(
                [str(binary), "--help"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertIn("does not request a GPIO", help_run.stdout)
            no_argument = subprocess.run(
                [str(binary)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(no_argument.returncode, 2)
            self.assertIn("reserved for initramfs PID 1", no_argument.stderr)


if __name__ == "__main__":
    unittest.main()
