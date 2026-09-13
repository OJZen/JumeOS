#!/usr/bin/env python3
"""Focused gates for the current-card first-version p1 deployment plan."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
GENERATOR_PATH = (
    REPO / "mainline/scripts/generate-r46h-first-version-p1-write-plan.py"
)
SPEC = importlib.util.spec_from_file_location(
    "r46h_first_version_release_deploy", GENERATOR_PATH
)
assert SPEC is not None and SPEC.loader is not None
GENERATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GENERATOR
SPEC.loader.exec_module(GENERATOR)
RELEASE_DIR = (
    REPO
    / "mainline/out/r46h-first-version-release/builds/"
    "build-2e0d33a53f11-e1e8d9edb2f8"
)
README = REPO / "mainline/first-version-release/README.md"
MANIFEST_SHA256 = "e1e8d9edb2f8d0a9fcb4c3a660547944adc0beabbb8d716b2db247b0e7ea588b"


def synthetic_release() -> object:
    return GENERATOR.ReleaseInputs(
        directory=Path("/tmp/release"),
        manifest_sha256="1" * 64,
        source_git_commit="2" * 40,
        prefix_sha256="3" * 64,
        p1_path=Path("/tmp/release/01-boot-p1.img"),
        p1_sha256="4" * 64,
        p2_sha256="5" * 64,
        p3_sha256="6" * 64,
    )


class R46HFirstVersionReleaseDeployTests(unittest.TestCase):
    def test_canonical_release_is_manifest_bound(self) -> None:
        if not RELEASE_DIR.is_dir():
            self.skipTest("canonical first-version release generation is absent")
        release = GENERATOR.load_release(REPO, RELEASE_DIR, MANIFEST_SHA256)
        self.assertEqual(release.manifest_sha256, MANIFEST_SHA256)
        self.assertEqual(
            release.p1_sha256,
            "c6f0d3a9dee4856922fa31cefab1cfae74c0e41364d05cfe36041dacb81ee6bb",
        )
        self.assertEqual(
            release.p2_sha256,
            "ee7d402c06a750081b4c588c5162cca44d0e07fa4b544d5a59bef7629722aeca",
        )
        self.assertEqual(
            release.p3_sha256,
            "fe0ee7764f2e2e1f4b8451183f8cadc26e3a876847eb1bfa0569198438501fac",
        )
        with self.assertRaises(GENERATOR.PlanError):
            GENERATOR.load_release(REPO, RELEASE_DIR, "0" * 64)

    def test_manifest_parser_rejects_unknown_or_reordered_fields(self) -> None:
        if not RELEASE_DIR.is_dir():
            self.skipTest("canonical first-version release generation is absent")
        payload = (RELEASE_DIR / "ASSET-MANIFEST").read_bytes()
        parsed = GENERATOR.parse_manifest(payload)
        self.assertEqual(tuple(parsed), GENERATOR.MANIFEST_KEYS)
        with self.assertRaises(GENERATOR.PlanError):
            GENERATOR.parse_manifest(payload + b"unknown value\n")
        lines = payload.splitlines(keepends=True)
        with self.assertRaises(GENERATOR.PlanError):
            GENERATOR.parse_manifest(b"".join((lines[1], lines[0], *lines[2:])))

    def test_plan_writes_only_exact_boot_partition(self) -> None:
        release = synthetic_release()
        payload = GENERATOR.build_write_plan("/dev/disk42", release, "7" * 64)
        plan = json.loads(payload)
        self.assertEqual(plan["device"], "/dev/disk42")
        self.assertEqual(plan["profile_id"], GENERATOR.PROFILE_ID)
        self.assertEqual(len(plan["operations"]), 1)
        operation = plan["operations"][0]
        self.assertEqual(operation["partition"], "boot")
        self.assertEqual(operation["source_size"], GENERATOR.P1_SIZE)
        self.assertEqual(operation["source_sha256"], release.p1_sha256)
        self.assertEqual(operation["target_sha256_before"], "7" * 64)
        self.assertNotIn("root", payload.decode())
        self.assertNotIn("easyroms", payload.decode())

    def test_plan_accepts_dynamic_disk_number_and_rejects_noop(self) -> None:
        release = synthetic_release()
        plan = json.loads(
            GENERATOR.build_write_plan("/dev/disk6", release, "8" * 64)
        )
        self.assertEqual(plan["device"], "/dev/disk6")
        for device in ("/dev/rdisk8", "/dev/disk0", "/dev/disk", "disk8"):
            with self.assertRaises(GENERATOR.PlanError):
                GENERATOR.build_write_plan(device, release, "8" * 64)
        with self.assertRaises(GENERATOR.PlanError):
            GENERATOR.build_write_plan("/dev/disk8", release, release.p1_sha256)

    def test_rollback_clone_must_be_exact_and_below_agent_sessions(self) -> None:
        sessions = REPO / "mainline/out/r46h-card-agent-sessions"
        sessions.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".test-first-version-deploy.", dir=sessions
        ) as temporary:
            clone = Path(temporary) / "p1-before.img"
            clone.write_bytes(b"rollback")
            digest = hashlib.sha256(b"rollback").hexdigest()
            with mock.patch.object(GENERATOR, "P1_SIZE", len(b"rollback")):
                resolved, actual = GENERATOR.load_rollback_clone(
                    REPO, clone, digest
                )
                self.assertEqual(resolved, clone.resolve())
                self.assertEqual(actual, digest)
                with self.assertRaises(GENERATOR.PlanError):
                    GENERATOR.load_rollback_clone(REPO, clone, "9" * 64)

    def test_create_plan_integrates_release_clone_and_receipt(self) -> None:
        if not RELEASE_DIR.is_dir():
            self.skipTest("canonical first-version release generation is absent")
        sessions = REPO / "mainline/out/r46h-card-agent-sessions"
        cache = REPO / "mainline/out/.cache"
        sessions.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".test-first-version-audit.", dir=sessions
        ) as audit_temporary, tempfile.TemporaryDirectory(
            prefix=".test-first-version-plans.", dir=cache
        ) as plan_temporary:
            clone = Path(audit_temporary) / "p1-before.img"
            with clone.open("wb") as handle:
                handle.truncate(GENERATOR.P1_SIZE)
            target_sha256 = GENERATOR.sha256_file(clone)
            with redirect_stdout(io.StringIO()):
                plan_dir = GENERATOR.create_plan(
                    REPO,
                    RELEASE_DIR,
                    MANIFEST_SHA256,
                    clone,
                    target_sha256,
                    "/dev/disk42",
                    "/dev/disk42",
                    Path(plan_temporary),
                )
            plan_payload = (plan_dir / "write-plan.json").read_bytes()
            plan_sha256 = hashlib.sha256(plan_payload).hexdigest()
            self.assertEqual(
                (plan_dir / "write-plan.sha256").read_text(encoding="utf-8"),
                f"{plan_sha256}  write-plan.json\n",
            )
            info = (plan_dir / "PLAN-INFO").read_text(encoding="utf-8")
            self.assertIn(f"release_manifest_sha256={MANIFEST_SHA256}\n", info)
            self.assertIn(f"rollback_clone_sha256={target_sha256}\n", info)
            self.assertIn("postwrite_contract=full-hash-prefix-p1-p2-p3\n", info)

    def test_generator_does_not_open_a_physical_device(self) -> None:
        source = GENERATOR_PATH.read_text(encoding="utf-8")
        self.assertIn('"physical_device_reads=0\\n"', source)
        self.assertIn('"media_writes=0\\n"', source)
        self.assertIn('"rollback clone parent"', source)
        self.assertNotIn('open("/dev/', source)
        self.assertNotIn("subprocess", source)

    def test_readme_pins_closed_historical_card_convergence_boundary(self) -> None:
        text = README.read_text(encoding="utf-8")
        collapsed = " ".join(
            line.removeprefix("> ").strip() for line in text.splitlines()
        )
        for marker in (
            "Historical release convergence (completed 2026-08-26)",
            "closed record of the release-card convergence",
            "not an instruction for the current card",
            "do not replay the commands below against current media",
            "audited all four complete ranges and wrote each differing partition",
            "required p1, p2 and p3",
            "generate-r46h-first-version-p1-write-plan.py",
            "generate-debian13-write-plan.py",
            "--variant fast-card-62534975488",
            "clone boot first-version-p1-before.img",
            "hash-raw easyroms",
            "a differing final hash would have blocked that boot",
        ):
            self.assertIn(marker, collapsed)
        self.assertNotIn("## Current-card convergence", text)
        self.assertNotIn("already has exact p2 v0.5 and exact p3", text)
        self.assertNotIn("Rewriting those identical 62 GB", text)


if __name__ == "__main__":
    unittest.main()
