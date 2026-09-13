#!/usr/bin/env python3
"""Unit tests for the macOS read-only privilege launcher.

These tests never enumerate or open a physical device.  All disposable files
are created below mainline/out on the external workspace volume.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import types
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_PATH = REPO_ROOT / "mainline" / "scripts" / "r46h_card_macos_readonly.py"
SPEC = importlib.util.spec_from_file_location("r46h_card_macos_readonly_tests", LAUNCHER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load launcher: {LAUNCHER_PATH}")
LAUNCHER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = LAUNCHER
SPEC.loader.exec_module(LAUNCHER)
SHARED_LAYOUT_ID_GOLDEN = (
    "r46h-profile-bound-layout-v1:"
    "ed2f77b270ef0827f6ef69a32a227c76847cb23565ea95c8b7b3215a65687743"
)


class MacReadOnlyLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scratch_root = (
            REPO_ROOT / "mainline" / "out" / ".cache" / "r46h-card-launcher-tests"
        )
        cls.scratch_root.mkdir(mode=0o700, parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.scratch_root.rmdir()
        except OSError:
            pass

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="unit-", dir=self.scratch_root
        )
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def profile(self) -> dict[str, object]:
        return {
            "format_version": 2,
            "profile_id": "hl-r46h-test-v2",
            "target": "HL-R46H-V22",
            "whole_size": 4096,
            "sector_size": 512,
            "partition_scheme": "mbr",
            "prefix": {"size": 512, "sha256": "1" * 64},
            "partitions": [
                {
                    "role": "boot",
                    "number": 1,
                    "offset": 512,
                    "size": 1024,
                    "mbr": {"bootable": False, "type_code": 12},
                    "filesystem": "fat32",
                    "identifiers": {"volume_uuid": "A-B"},
                },
                {
                    "role": "root",
                    "number": 2,
                    "offset": 1536,
                    "size": 2560,
                    "mbr": {"bootable": False, "type_code": 131},
                    "filesystem": "ext4",
                    "identifiers": {"partuuid": "00000001-02"},
                },
            ],
        }

    def candidate(self, attachment_id: str = "macos-iomedia-v1:abc") -> dict[str, object]:
        return {
            "platform": "macos",
            "attachment_id": attachment_id,
            "physical_store_id": "ioreg:1",
            "display_path": "/dev/rdisk-test-placeholder",
            "transport": "USB",
            "size": 4096,
            "sector_size": 512,
            "whole": True,
            "internal": False,
            "removable": True,
            "ejectable": True,
            "writable": True,
            "system_disk": False,
        }

    def bindings(self) -> object:
        generation = self.root / "build-a"
        return LAUNCHER.ReleaseBindings(
            repo_root=self.root,
            generation=generation,
            git_commit="a" * 40,
            binary=self.root / "r46h-card",
            binary_sha256="2" * 64,
            binary_size=123,
            tool_version="0.2.0",
            profile=self.root / "profile.json",
            profile_sha256="3" * 64,
            profile_size=456,
            profile_payload=self.profile(),
        )

    def receipt_files(self) -> dict[str, bytes]:
        bindings = self.bindings()
        receipt = {
            "format_version": 1,
            "audit_id": "audit-1",
            "profile_id": "hl-r46h-test-v2",
            "profile_sha256": bindings.profile_sha256,
            "tool_version": "0.2.0",
            "tool_sha256": bindings.binary_sha256,
            "hardware_target": "HL-R46H-V22",
            "layout_id": "",
            "candidate": self.candidate(),
            "partition_scheme": "mbr",
            "prefix_size": 512,
            "prefix_sha256": "1" * 64,
            "mbr_disk_signature": 1,
            "partitions": [
                {
                    "role": "boot",
                    "number": 1,
                    "offset": 512,
                    "size": 1024,
                    "mbr_bootable": False,
                    "mbr_type_code": 12,
                    "filesystem": "fat32",
                    "identifiers": {"volume_uuid": "A-B"},
                },
                {
                    "role": "root",
                    "number": 2,
                    "offset": 1536,
                    "size": 2560,
                    "mbr_bootable": False,
                    "mbr_type_code": 131,
                    "filesystem": "ext4",
                    "identifiers": {"partuuid": "00000001-02"},
                },
            ],
            "media_access": "read_only",
            "ejected": True,
        }
        receipt["layout_id"] = LAUNCHER.recompute_layout_id(receipt)
        receipt_bytes = (json.dumps(receipt, sort_keys=True) + "\n").encode("utf-8")
        return {
            "READONLY-AUDIT.json": receipt_bytes,
            "AUDIT-COMPLETE": (
                "receipt_sha256=" + hashlib.sha256(receipt_bytes).hexdigest() + "\n"
            ).encode("ascii"),
        }

    def test_discovery_parser_requires_exact_eligible_candidate(self) -> None:
        candidate = self.candidate()
        payload = (json.dumps(candidate) + "\n").encode("utf-8")
        self.assertEqual(LAUNCHER.parse_discovery(payload), [candidate])

        duplicate = payload + payload
        with self.assertRaisesRegex(LAUNCHER.LauncherError, "duplicate attachment"):
            LAUNCHER.parse_discovery(duplicate)

        candidate["internal"] = True
        with self.assertRaisesRegex(LAUNCHER.LauncherError, "ineligible"):
            LAUNCHER.parse_discovery((json.dumps(candidate) + "\n").encode())

    def test_selection_is_explicit_and_profile_bound(self) -> None:
        candidate = self.candidate()
        selected = LAUNCHER.select_candidate(
            [candidate], candidate["attachment_id"], self.profile()
        )
        self.assertIs(selected, candidate)
        with self.assertRaisesRegex(LAUNCHER.LauncherError, "matched 0"):
            LAUNCHER.select_candidate([candidate], "another", self.profile())
        candidate["size"] = 8192
        with self.assertRaisesRegex(LAUNCHER.LauncherError, "geometry"):
            LAUNCHER.select_candidate(
                [candidate], candidate["attachment_id"], self.profile()
            )

    def test_completed_receipt_is_bound_to_profile_tool_and_marker(self) -> None:
        files = self.receipt_files()
        receipt = LAUNCHER.validate_completed_receipt(
            files, self.bindings(), self.candidate(), "audit-1"
        )
        self.assertEqual(receipt["tool_sha256"], "2" * 64)

        altered = dict(files)
        payload = json.loads(altered["READONLY-AUDIT.json"])
        payload["tool_sha256"] = "9" * 64
        altered["READONLY-AUDIT.json"] = (json.dumps(payload) + "\n").encode()
        altered["AUDIT-COMPLETE"] = (
            "receipt_sha256="
            + hashlib.sha256(altered["READONLY-AUDIT.json"]).hexdigest()
            + "\n"
        ).encode()
        with self.assertRaisesRegex(LAUNCHER.LauncherError, "pinned audit bindings"):
            LAUNCHER.validate_completed_receipt(
                altered, self.bindings(), self.candidate(), "audit-1"
            )

        bad_marker = dict(files)
        bad_marker["AUDIT-COMPLETE"] = b"receipt_sha256=" + b"0" * 64 + b"\n"
        with self.assertRaisesRegex(LAUNCHER.LauncherError, "does not bind"):
            LAUNCHER.validate_completed_receipt(
                bad_marker, self.bindings(), self.candidate(), "audit-1"
            )

        wrong_layout = dict(files)
        payload = json.loads(wrong_layout["READONLY-AUDIT.json"])
        payload["layout_id"] = "r46h-profile-bound-layout-v1:" + "0" * 64
        wrong_layout["READONLY-AUDIT.json"] = (json.dumps(payload) + "\n").encode()
        wrong_layout["AUDIT-COMPLETE"] = (
            "receipt_sha256="
            + hashlib.sha256(wrong_layout["READONLY-AUDIT.json"]).hexdigest()
            + "\n"
        ).encode()
        with self.assertRaisesRegex(LAUNCHER.LauncherError, "layout identity"):
            LAUNCHER.validate_completed_receipt(
                wrong_layout, self.bindings(), self.candidate(), "audit-1"
            )

        wrong_signature = dict(files)
        payload = json.loads(wrong_signature["READONLY-AUDIT.json"])
        payload["mbr_disk_signature"] = 2
        payload["layout_id"] = LAUNCHER.recompute_layout_id(payload)
        wrong_signature["READONLY-AUDIT.json"] = (json.dumps(payload) + "\n").encode()
        wrong_signature["AUDIT-COMPLETE"] = (
            "receipt_sha256="
            + hashlib.sha256(wrong_signature["READONLY-AUDIT.json"]).hexdigest()
            + "\n"
        ).encode()
        with self.assertRaisesRegex(LAUNCHER.LauncherError, "PARTUUID"):
            LAUNCHER.validate_completed_receipt(
                wrong_signature, self.bindings(), self.candidate(), "audit-1"
            )

        for path in (("safe_to_boot",), ("candidate", "safe_to_boot"), ("partitions", 0, "write_authorized")):
            unknown = dict(files)
            payload = json.loads(unknown["READONLY-AUDIT.json"])
            target = payload
            for component in path[:-1]:
                target = target[component]
            target[path[-1]] = True
            unknown["READONLY-AUDIT.json"] = (json.dumps(payload) + "\n").encode()
            unknown["AUDIT-COMPLETE"] = (
                "receipt_sha256="
                + hashlib.sha256(unknown["READONLY-AUDIT.json"]).hexdigest()
                + "\n"
            ).encode()
            with self.assertRaises(LAUNCHER.LauncherError):
                LAUNCHER.validate_completed_receipt(
                    unknown, self.bindings(), self.candidate(), "audit-1"
                )

        duplicate = files["READONLY-AUDIT.json"].replace(
            b'"ejected": true', b'"ejected": true, "ejected": true', 1
        )
        duplicate_files = {
            "READONLY-AUDIT.json": duplicate,
            "AUDIT-COMPLETE": (
                "receipt_sha256=" + hashlib.sha256(duplicate).hexdigest() + "\n"
            ).encode(),
        }
        with self.assertRaisesRegex(LAUNCHER.LauncherError, "invalid read-only audit receipt JSON"):
            LAUNCHER.validate_completed_receipt(
                duplicate_files, self.bindings(), self.candidate(), "audit-1"
            )

    def test_layout_identity_matches_rust_golden_vector(self) -> None:
        receipt = json.loads(self.receipt_files()["READONLY-AUDIT.json"])
        self.assertEqual(receipt["layout_id"], SHARED_LAYOUT_ID_GOLDEN)
        self.assertEqual(LAUNCHER.recompute_layout_id(receipt), SHARED_LAYOUT_ID_GOLDEN)

    def test_handoff_envelope_is_nonce_scoped_and_size_bounded(self) -> None:
        token = "a" * 32
        files = self.receipt_files()
        envelope = {
            "schema": LAUNCHER.HANDOFF_SCHEMA,
            "status": "complete",
            "returncode": 0,
            "evidence_name": ".r46h-card-readonly-audit." + "b" * 32,
            "files": {
                name: base64.b64encode(payload).decode("ascii")
                for name, payload in files.items()
            },
        }
        line = (
            f"{LAUNCHER.HANDOFF_PREFIX}:{token}:".encode()
            + base64.b64encode(json.dumps(envelope).encode())
            + b"\n"
        )
        result = LAUNCHER.parse_handoff_line(line, token)
        self.assertEqual(result.files, files)
        with self.assertRaisesRegex(LAUNCHER.LauncherError, "prefix"):
            LAUNCHER.parse_handoff_line(line, "c" * 32)

        envelope["files"]["READONLY-AUDIT.json"] = base64.b64encode(
            b"x" * (LAUNCHER.MAX_RECEIPT_FILE_BYTES + 1)
        ).decode()
        oversized = (
            f"{LAUNCHER.HANDOFF_PREFIX}:{token}:".encode()
            + base64.b64encode(json.dumps(envelope).encode())
        )
        with self.assertRaisesRegex(LAUNCHER.LauncherError, "size bound"):
            LAUNCHER.parse_handoff_line(oversized, token)

    def test_archive_is_flat_no_clobber_and_completion_last(self) -> None:
        archive_root = self.root / "archive"
        archive_root.mkdir()
        files = self.receipt_files()
        write_order = []
        original_write = LAUNCHER._write_new_at

        def record_write(directory: int, name: str, payload: bytes, mode: int = 0o600) -> None:
            write_order.append(name)
            original_write(directory, name, payload, mode)

        with mock.patch.object(LAUNCHER, "_write_new_at", side_effect=record_write):
            output = LAUNCHER.publish_handoff_archive(
                archive_root,
                files,
                "complete",
                self.bindings(),
                "macos-iomedia-v1:abc",
                "audit-1",
            )
        self.assertEqual(
            write_order,
            [
                "READONLY-AUDIT.json",
                "AUDIT-COMPLETE",
                "HANDOFF.json",
                "HANDOFF-COMPLETE",
            ],
        )
        self.assertEqual(
            {path.name for path in output.iterdir()},
            {
                "READONLY-AUDIT.json",
                "AUDIT-COMPLETE",
                "HANDOFF.json",
                "HANDOFF-COMPLETE",
            },
        )
        manifest_bytes = (output / "HANDOFF.json").read_bytes()
        self.assertEqual(
            (output / "HANDOFF-COMPLETE").read_text(),
            "handoff_sha256=" + hashlib.sha256(manifest_bytes).hexdigest() + "\nstatus=complete\n",
        )
        with self.assertRaisesRegex(LAUNCHER.LauncherError, "already exists"):
            LAUNCHER.publish_handoff_archive(
                archive_root,
                files,
                "complete",
                self.bindings(),
                "macos-iomedia-v1:abc",
                "audit-1",
            )

        def fail_manifest(directory: int, name: str, payload: bytes, mode: int = 0o600) -> None:
            if name == "HANDOFF.json":
                raise OSError("injected manifest failure")
            original_write(directory, name, payload, mode)

        with mock.patch.object(LAUNCHER, "_write_new_at", side_effect=fail_manifest):
            with self.assertRaisesRegex(OSError, "injected manifest failure"):
                LAUNCHER.publish_handoff_archive(
                    archive_root,
                    files,
                    "complete",
                    self.bindings(),
                    "macos-iomedia-v1:abc",
                    "audit-interrupted",
                )
        partial = archive_root / "r46h-readonly-audit-interrupted"
        self.assertTrue((partial / "AUDIT-COMPLETE").is_file())
        self.assertFalse((partial / "HANDOFF-COMPLETE").exists())

    def test_archive_failure_reports_exact_recovery_evidence_path(self) -> None:
        evidence_name = ".r46h-card-readonly-audit." + "e" * 32
        result = LAUNCHER.PrivilegedResult(
            returncode=0,
            evidence_name=evidence_name,
            status="complete",
            files=self.receipt_files(),
        )
        archive = self.root / "archive-recovery"
        archive.mkdir()
        descriptor = os.open(archive, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        metadata = os.fstat(descriptor)
        handle = LAUNCHER.ArchiveRootHandle(
            archive, descriptor, metadata.st_dev, metadata.st_ino, "disk6"
        )
        stderr = io.StringIO()
        try:
            with mock.patch.object(
                LAUNCHER,
                "revalidate_external_archive_root",
                side_effect=LAUNCHER.LauncherError("injected archive drift"),
            ), mock.patch.object(LAUNCHER.sys, "stderr", stderr):
                with self.assertRaisesRegex(LAUNCHER.LauncherError, "archive drift"):
                    LAUNCHER.validate_and_publish_privileged_result(
                        handle,
                        object(),
                        result,
                        self.bindings(),
                        self.candidate(),
                        "macos-iomedia-v1:abc",
                        "audit-1",
                    )
        finally:
            os.close(descriptor)
        self.assertEqual(
            stderr.getvalue(),
            f"WARNING: recovery evidence remains at /private/tmp/{evidence_name}\n",
        )
        self.assertEqual(list(archive.iterdir()), [])

    def test_temporary_cleanup_requires_exact_unchanged_flat_evidence(self) -> None:
        files = self.receipt_files()
        evidence_name = ".r46h-card-readonly-audit." + "d" * 32
        evidence = self.root / evidence_name
        evidence.mkdir(mode=0o700)
        for name, payload in files.items():
            (evidence / name).write_bytes(payload)
        self.assertTrue(
            LAUNCHER.cleanup_temporary_evidence(
                evidence_name, files, _parent=self.root
            )
        )
        self.assertFalse(evidence.exists())

        evidence.mkdir(mode=0o700)
        for name, payload in files.items():
            (evidence / name).write_bytes(payload)
        (evidence / "READONLY-AUDIT.json").write_bytes(b"changed")
        self.assertFalse(
            LAUNCHER.cleanup_temporary_evidence(
                evidence_name, files, _parent=self.root
            )
        )
        self.assertTrue(evidence.exists())

    def test_archive_root_is_proven_external_before_creation(self) -> None:
        external = types.SimpleNamespace(internal=False, physical_id="disk6")
        driver = types.SimpleNamespace(query_macos_storage_identity=mock.Mock(return_value=external))
        path = self.root / "existing-archive"
        path.mkdir()
        self.assertEqual(
            LAUNCHER.prepare_external_archive_root(path, driver, platform_name="darwin"),
            path,
        )
        self.assertGreaterEqual(driver.query_macos_storage_identity.call_count, 2)

        missing = self.root / "must-already-exist"
        with self.assertRaisesRegex(LAUNCHER.LauncherError, "must already exist"):
            LAUNCHER.prepare_external_archive_root(
                missing, driver, platform_name="darwin"
            )
        self.assertFalse(missing.exists())

        internal_driver = types.SimpleNamespace(
            query_macos_storage_identity=mock.Mock(
                return_value=types.SimpleNamespace(internal=True, physical_id="disk1")
            )
        )
        rejected = self.root / "must-not-be-created"
        rejected.mkdir()
        with self.assertRaisesRegex(LAUNCHER.LauncherError, "external macOS storage"):
            LAUNCHER.prepare_external_archive_root(
                rejected, internal_driver, platform_name="darwin"
            )
        self.assertEqual(list(rejected.iterdir()), [])

    def test_target_card_existing_archive_is_rejected_before_any_child_creation(self) -> None:
        target_driver = types.SimpleNamespace(
            query_macos_storage_identity=mock.Mock(
                return_value=types.SimpleNamespace(internal=False, physical_id="disk12")
            )
        )
        rejected = self.root / "existing-target-card-root"
        rejected.mkdir()
        with self.assertRaisesRegex(LAUNCHER.LauncherError, "target card"):
            LAUNCHER.prepare_external_archive_root(
                rejected,
                target_driver,
                platform_name="darwin",
                forbidden_physical_id="disk12",
            )
        self.assertEqual(list(rejected.iterdir()), [])

    def test_archive_physical_store_must_differ_from_target(self) -> None:
        archive = self.root / "archive-store"
        archive.mkdir()
        descriptor = os.open(archive, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        metadata = os.fstat(descriptor)
        candidate = self.candidate()
        candidate["display_path"] = "/dev/rdisk12"
        handle = LAUNCHER.ArchiveRootHandle(
            archive, descriptor, metadata.st_dev, metadata.st_ino, "disk12"
        )
        try:
            with self.assertRaisesRegex(LAUNCHER.LauncherError, "target card"):
                LAUNCHER.require_archive_target_separation(handle, candidate)
            different = dataclasses.replace(handle, physical_id="disk6")
            LAUNCHER.require_archive_target_separation(different, candidate)
        finally:
            os.close(descriptor)

    def test_release_collection_uses_validated_generation_and_manifest_binding(self) -> None:
        repo = self.root / "repo"
        generation = repo / "generation"
        profile_path = repo / Path(LAUNCHER.PROFILE_RELATIVE_PATH.as_posix())
        profile_path.parent.mkdir(parents=True)
        generation.mkdir(parents=True)
        binary_payload = b"binary-v02"
        profile_payload = json.dumps(self.profile(), sort_keys=True).encode()
        (generation / "r46h-card").write_bytes(binary_payload)
        profile_path.write_bytes(profile_payload)
        manifest = {
            "files": [
                {
                    "path": LAUNCHER.PROFILE_RELATIVE_PATH.as_posix(),
                    "size": len(profile_payload),
                    "sha256": hashlib.sha256(profile_payload).hexdigest(),
                }
            ]
        }
        build_receipt = {
            "artifact": {
                "path": "r46h-card",
                "size": len(binary_payload),
                "sha256": hashlib.sha256(binary_payload).hexdigest(),
            },
            "source": {"git_commit": "a" * 40},
        }
        (generation / "SOURCE-MANIFEST.json").write_text(json.dumps(manifest))
        (generation / "BUILD-RECEIPT.json").write_text(json.dumps(build_receipt))
        validator = mock.Mock(return_value=generation)
        fake_driver = types.SimpleNamespace(
            make_layout=mock.Mock(return_value=object()),
            validate_release_generation=validator,
        )
        version = subprocess_result(stdout=b"r46h-card 0.2.0\n")
        profile_sha256 = hashlib.sha256(profile_payload).hexdigest()
        schema = subprocess_result(
            stdout=(
                "R46H_CARD_READONLY_SCHEMA result=pass format_version=2 "
                f"profile_sha256={profile_sha256}\n"
            ).encode()
        )
        with mock.patch.object(LAUNCHER, "_load_build_driver", return_value=fake_driver), mock.patch.object(
            LAUNCHER.subprocess, "run", side_effect=[version, schema]
        ):
            bindings = LAUNCHER.collect_release_bindings(repo)
        validator.assert_called_once()
        self.assertEqual(bindings.profile_sha256, hashlib.sha256(profile_payload).hexdigest())
        self.assertEqual(bindings.binary_sha256, hashlib.sha256(binary_payload).hexdigest())

        profile_path.write_bytes(profile_payload + b" ")
        with mock.patch.object(LAUNCHER, "_load_build_driver", return_value=fake_driver):
            with self.assertRaisesRegex(LAUNCHER.LauncherError, "clean-HEAD"):
                LAUNCHER.collect_release_bindings(repo)

    def test_build_driver_python_gate_runs_when_loaded_as_a_module(self) -> None:
        if sys.version_info < (3, 10):
            with self.assertRaisesRegex(
                LAUNCHER.LauncherError, "Python 3.10 or newer"
            ) as caught:
                LAUNCHER._load_build_driver(REPO_ROOT)
            self.assertEqual(caught.exception.exit_code, LAUNCHER.EX_UNAVAILABLE)
        else:
            driver = LAUNCHER._load_build_driver(REPO_ROOT)
            self.assertTrue(callable(driver.require_supported_python))

    def test_privileged_bootstrap_uses_no_shell_and_drops_ids_for_source_open(self) -> None:
        source = LAUNCHER.PRIVILEGED_BOOTSTRAP
        self.assertNotIn("shell=True", source)
        self.assertNotIn("/bin/bash", source)
        self.assertIn("os.seteuid(CALLER_UID)", source)
        self.assertIn("os.setgroups([CALLER_GID])", source)
        self.assertIn("os.setgroups([])", source)
        self.assertNotIn("original_groups", source)
        self.assertIn("source bytes do not match the pre-sudo binding", source)
        self.assertNotIn("start_new_session=True", source)
        self.assertIn("child.send_signal(signum)", source)
        self.assertNotIn("os.killpg(child.pid", source)
        self.assertIn("cleanup_stage(stage, active_stage_fd)", source)

        cli_source = (
            REPO_ROOT
            / "mainline"
            / "tools"
            / "r46h-card-toolchain"
            / "crates"
            / "r46h-card-cli"
            / "src"
            / "main.rs"
        ).read_text(encoding="utf-8")
        self.assertNotIn("remove_empty_reserved_evidence", cli_source)
        self.assertGreaterEqual(cli_source.count("publish_readonly_failure("), 3)

    def test_sudo_authorization_is_foreground_then_audit_is_noninteractive(self) -> None:
        LAUNCHER.authorize_sudo(
            _command=[sys.executable, "-I", "-B", "-c", "raise SystemExit(0)"],
            _timeout_seconds=5,
        )

        with mock.patch.object(LAUNCHER.sys, "platform", "darwin"), mock.patch.object(
            LAUNCHER.Path, "is_file", return_value=True
        ):
            command = LAUNCHER.privileged_command(
                self.bindings(),
                "macos-iomedia-v1:abc",
                "audit-1",
                ".r46h-card-readonly-audit." + "a" * 32,
                "b" * 32,
                501,
                20,
            )
        sudo_index = command.index("/usr/bin/sudo")
        self.assertEqual(command[sudo_index + 1 : sudo_index + 3], ["-n", "--"])

    def test_sigterm_during_foreground_authorization_reaps_child(self) -> None:
        fake = r'''
import signal, time
def stop(_signum, _frame):
    raise SystemExit(143)
signal.signal(signal.SIGTERM, stop)
print("FAKE_AUTH_READY", flush=True)
while True:
    time.sleep(1)
'''
        old_alarm = signal.signal(
            signal.SIGALRM,
            lambda _signum, _frame: os.kill(os.getpid(), signal.SIGTERM),
        )
        signal.setitimer(signal.ITIMER_REAL, 0.25)
        try:
            with self.assertRaisesRegex(LAUNCHER.LauncherError, "was interrupted") as raised:
                LAUNCHER.authorize_sudo(
                    _command=[sys.executable, "-I", "-B", "-c", fake],
                    _timeout_seconds=5,
                )
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_alarm)
        self.assertEqual(raised.exception.exit_code, 128 + signal.SIGTERM)

    def test_parent_sigterm_is_forwarded_to_privileged_process_group(self) -> None:
        token = "e" * 32
        evidence_name = ".r46h-card-readonly-audit." + "f" * 32
        fake = r'''
import base64, json, signal, sys, time
token, evidence = sys.argv[1:]
def stop(_signum, _frame):
    envelope = {
        "schema": "r46h-card-macos-readonly-handoff/v1",
        "status": "failed",
        "returncode": 143,
        "evidence_name": evidence,
        "files": {"AUDIT-FAILED": base64.b64encode(b"signal-forwarded\n").decode("ascii")},
    }
    encoded = base64.b64encode(json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("ascii")).decode("ascii")
    print("R46H_CARD_HANDOFF_V1:" + token + ":" + encoded, flush=True)
    raise SystemExit(143)
signal.signal(signal.SIGTERM, stop)
print("FAKE_READY", flush=True)
while True:
    time.sleep(1)
'''
        old_alarm = signal.signal(
            signal.SIGALRM,
            lambda _signum, _frame: os.kill(os.getpid(), signal.SIGTERM),
        )
        signal.setitimer(signal.ITIMER_REAL, 0.25)
        try:
            with self.assertRaisesRegex(
                LAUNCHER.LauncherError, "was interrupted"
            ) as raised:
                LAUNCHER.run_privileged(
                    [sys.executable, "-I", "-B", "-c", fake, token, evidence_name],
                    token,
                    evidence_name,
                )
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_alarm)
        self.assertEqual(raised.exception.exit_code, 143)


def subprocess_result(*, stdout: bytes) -> object:
    return types.SimpleNamespace(stdout=stdout, stderr=b"", returncode=0)


if __name__ == "__main__":
    unittest.main()
