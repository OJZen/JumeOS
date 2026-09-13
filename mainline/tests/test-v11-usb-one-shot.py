#!/usr/bin/env python3
"""Focused host tests for the R46H v0.11 read-only USB one-shot payload."""

from __future__ import annotations

import gzip
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-v11-usb-one-shot.py"
OBSERVER_PATH = REPO / "mainline/bringup-tests/r46h-v11-charger-observe.c"
RUNBOOK_PATH = REPO / "mainline/bringup-tests/V11-USB-DC-ONE-SHOT.md"


def load_builder():
    spec = importlib.util.spec_from_file_location("v11_usb_builder", BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER = load_builder()


class V11UsbOneShotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = BUILDER_PATH.read_text()
        cls.observer = OBSERVER_PATH.read_text()
        cls.runbook = RUNBOOK_PATH.read_text()

    def test_canonical_package_and_artifact_constants_are_exact(self) -> None:
        self.assertEqual(BUILDER.PACKAGE_SIZE, BUILDER.PACKAGE_TAR.stat().st_size)
        self.assertEqual(BUILDER.PACKAGE_SHA256, BUILDER.sha256_file(BUILDER.PACKAGE_TAR))
        self.assertEqual(
            BUILDER.PACKAGE_SOURCE_COMMIT,
            "88a1e31a35c84091a15c3c326e97b79b948c5920",
        )
        self.assertEqual(BUILDER.IMAGE_SIZE, 41_570_816)
        self.assertEqual(BUILDER.DTB_SIZE, 49_518)
        self.assertEqual(BUILDER.CHARGER_SIZE, 27_024)

    def test_boot_script_is_usb_only_and_rollback_safe(self) -> None:
        rendered = BUILDER.render_boot_script(0x1234, BUILDER.IMAGE_SIZE, BUILDER.DTB_SIZE)
        text = rendered.decode()
        self.assertEqual(text.count("fatload usb 0:1"), 2)
        self.assertIn("R46HV11/IMAGE.GZ", text)
        self.assertIn("R46HV11/R46H.DTB", text)
        self.assertIn("root=PARTUUID=c9f931c9-02", text)
        self.assertIn(" rootwait ro init=/bin/bash ", text)
        self.assertIn("itest ${filesize} -eq 0x1234", text)
        for forbidden in (
            "saveenv",
            "mmc write",
            "fatwrite",
            "load mmc",
            "setexpr",
            " rootwait rw ",
            "fsck.repair",
        ):
            self.assertNotIn(forbidden, text)

    def test_deterministic_gzip_round_trip(self) -> None:
        source = bytes(range(256)) * 32
        first = BUILDER.deterministic_gzip(source)
        second = BUILDER.deterministic_gzip(source)
        self.assertEqual(first, second)
        self.assertEqual(gzip.decompress(first), source)
        self.assertEqual(first[4:8], b"\0\0\0\0")

    def test_generation_name_is_strict_and_portable(self) -> None:
        self.assertTrue(
            BUILDER.valid_generation_name("build-0123456789ab-cdef01234567")
        )
        for value in (
            "build-0123456789ab-cdef0123456",
            "build-0123456789AB-cdef01234567",
            "build-../../escape-0123456789ab",
            "other-0123456789ab-cdef01234567",
            None,
        ):
            self.assertFalse(BUILDER.valid_generation_name(value))

    def test_staged_validation_uses_the_intended_final_name(self) -> None:
        source = BUILDER.validate_generation.__code__.co_varnames
        self.assertIn("staged_generation_name", source)
        builder_source = BUILDER_PATH.read_text()
        self.assertIn(
            "validate_generation(stage, commit, generation_name)", builder_source
        )
        self.assertIn("validate_generation(generation, commit)", builder_source)

    def test_observer_never_requests_or_drives_the_gpio(self) -> None:
        self.assertIn("GPIO_V2_GET_LINEINFO_IOCTL", self.observer)
        self.assertNotIn("GPIO_V2_GET_LINE_IOCTL", self.observer)
        self.assertNotIn("GPIO_V2_LINE_SET_VALUES_IOCTL", self.observer)
        self.assertNotIn("GPIO_V2_LINE_FLAG_OUTPUT", self.observer)
        self.assertIn('strcmp(line_info.consumer, "rk817-dc-det")', self.observer)

    def test_observer_pins_release_dt_and_both_online_states(self) -> None:
        self.assertIn(BUILDER.KERNEL_RELEASE, self.observer)
        self.assertIn("dc-det-gpios", self.observer)
        self.assertIn("0x00, 0x0b", self.observer)
        self.assertIn("--expect-disconnected", self.observer)
        self.assertIn("--expect-connected", self.observer)
        self.assertIn("rk817_dc_det", self.observer)
        self.assertIn("charge-current-safety=not-proved", self.observer)

    def test_source_scope_contains_every_security_relevant_input(self) -> None:
        self.assertEqual(
            BUILDER.SOURCE_PATHS,
            (
                "mainline/scripts/build-v11-usb-one-shot.py",
                "mainline/scripts/stage-v11-usb-one-shot-macos.py",
                "mainline/scripts/generate-easyroms-bundle.py",
                "mainline/bringup-tests/r46h-v11-charger-observe.c",
                "mainline/bringup-tests/V11-USB-DC-ONE-SHOT.md",
                "mainline/tests/test-v11-usb-one-shot.py",
                "mainline/tests/test-v11-usb-stage-macos.py",
            ),
        )
        for relative in BUILDER.SOURCE_PATHS:
            self.assertTrue((REPO / relative).is_file())

    def test_runbook_preserves_transport_and_evidence_boundaries(self) -> None:
        normalized = " ".join(self.runbook.split())
        for literal in (
            "avoids another TF-card write or remove/reinsert cycle",
            "346d:5678",
            "8447981125795107445",
            "62,914,560,000",
            "R46HUSB",
            "AppleDouble",
            "already-present payload file has the expected size and SHA-256",
            "never runs `saveenv`",
            "does not enable or tune charging",
            "read-only rescue shell",
            "power off directly",
            "result=online-contract-pass",
            "28cf45861aefa732b664eaeaa4a13df8dad7fdadc2c44d93005035d85d338067",
            "orphan cleanup on readonly fs",
            "Invalid charge termination 52000, keeping default",
        ):
            self.assertIn(literal, normalized)

    def test_tree_manifest_is_sorted_and_excludes_completion_files(self) -> None:
        cache = REPO / "mainline/out/.cache"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            root = Path(temporary)
            (root / "b").write_bytes(b"second")
            (root / "a").write_bytes(b"first")
            (root / "SHA256SUMS").write_bytes(b"ignored")
            manifest = BUILDER.tree_manifest(root, {"SHA256SUMS"}).decode().splitlines()
        self.assertEqual([line.split("  ", 1)[1] for line in manifest], ["a", "b"])

    def test_tree_manifest_rejects_links_and_special_files(self) -> None:
        cache = REPO / "mainline/out/.cache"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            root = Path(temporary)
            (root / "real").write_bytes(b"payload")
            (root / "link").symlink_to("real")
            with self.assertRaises(BUILDER.BuildError):
                BUILDER.tree_manifest(root, set())

    def test_host_test_gate_uses_isolated_python_and_disables_integration(self) -> None:
        cache = REPO / "mainline/out/.cache"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            root = Path(temporary)
            source = root / "source"
            test_path = source / "mainline/tests/test-v11-usb-one-shot.py"
            test_path.parent.mkdir(parents=True)
            test_path.write_text("raise SystemExit(0)\n")
            package = root / "package.tar.gz"
            package.write_bytes(b"fixture")
            completed = subprocess.CompletedProcess([], 0)
            with mock.patch.object(
                BUILDER.subprocess, "run", return_value=completed
            ) as run:
                BUILDER.run_host_tests(source, package)
        self.assertEqual(run.call_count, 2)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(
            [Path(command[3]).name for command in commands],
            ["test-v11-usb-one-shot.py", "test-v11-usb-stage-macos.py"],
        )
        environment = run.call_args.kwargs["env"]
        self.assertTrue(
            all(command[1:3] == ["-I", "-B"] for command in commands)
        )
        self.assertEqual(environment["R46H_RUN_V11_USB_INTEGRATION"], "0")
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")

    @unittest.skipUnless(
        os.environ.get("R46H_RUN_V11_USB_INTEGRATION") == "1",
        "set R46H_RUN_V11_USB_INTEGRATION=1 for Docker/package integration",
    )
    def test_real_package_and_observer_compile(self) -> None:
        cache = REPO / "mainline/out/.cache"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            for relative in (
                "mainline/scripts/generate-easyroms-bundle.py",
                "mainline/bringup-tests/r46h-v11-charger-observe.c",
            ):
                destination = source / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((REPO / relative).read_bytes())
            validator = BUILDER.load_package_validator(source)
            snapshot = BUILDER.snapshot_package(root / "package.tar.gz")
            package, charger = BUILDER.require_package(snapshot, validator)
            observer, _, _ = BUILDER.compile_observer(root, source)
        self.assertEqual(BUILDER.sha256_bytes(package["image"]), BUILDER.IMAGE_SHA256)
        self.assertEqual(BUILDER.sha256_bytes(charger), BUILDER.CHARGER_SHA256)
        self.assertEqual(observer[:4], b"\x7fELF")


if __name__ == "__main__":
    unittest.main()
