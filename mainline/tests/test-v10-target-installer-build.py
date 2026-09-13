#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "mainline/scripts/build-r46h-v10-target-installer.py"
SPEC = importlib.util.spec_from_file_location("v10_target_builder", SCRIPT)
assert SPEC and SPEC.loader
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)
TEST_ROOT = ROOT / "mainline/out/.cache/r46h-v10-target-installer-build-tests"


class BuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = TEST_ROOT / f"fixture-{uuid.uuid4().hex}"
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        if TEST_ROOT.exists() and not any(TEST_ROOT.iterdir()):
            TEST_ROOT.rmdir()

    def test_elf_gate_accepts_only_aarch64_pie(self) -> None:
        value = bytearray(64)
        value[:6] = b"\x7fELF\x02\x01"
        value[16:18] = (3).to_bytes(2, "little")
        value[18:20] = (183).to_bytes(2, "little")
        BUILDER.verify_aarch64_elf(bytes(value))
        for offset, replacement in ((4, 1), (16, 2), (18, 62)):
            invalid = bytearray(value)
            if offset == 4:
                invalid[offset] = replacement
            else:
                invalid[offset : offset + 2] = replacement.to_bytes(2, "little")
            with self.assertRaises(BUILDER.BuildError):
                BUILDER.verify_aarch64_elf(bytes(invalid))

    def test_clean_snapshot_uses_head_blobs_and_rejects_dirty_scope(self) -> None:
        repo = self.root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", repo], check=True)
        subprocess.run(["git", "-C", repo, "config", "user.name", "test"], check=True)
        subprocess.run(
            ["git", "-C", repo, "config", "user.email", "test@example.invalid"],
            check=True,
        )
        (repo / "a").write_bytes(b"a\n")
        (repo / "b").write_bytes(b"b\n")
        subprocess.run(["git", "-C", repo, "add", "a", "b"], check=True)
        subprocess.run(["git", "-C", repo, "commit", "-qm", "fixture"], check=True)
        commit, _, captured, manifest = BUILDER.require_clean_snapshot(repo, ("a", "b"))
        self.assertEqual(captured, {"a": b"a\n", "b": b"b\n"})
        self.assertEqual(json.loads(manifest)["git_commit"], commit)
        (repo / "a").write_bytes(b"changed\n")
        with self.assertRaisesRegex(BUILDER.BuildError, "source scope"):
            BUILDER.require_clean_snapshot(repo, ("a", "b"))

    def test_safe_cache_root_is_external_repo_cache_child(self) -> None:
        accepted = BUILDER.safe_cache_root(str(BUILDER.CACHE_PARENT / "fixture"))
        self.assertEqual(accepted, BUILDER.CACHE_PARENT / "fixture")
        for rejected in (str(BUILDER.CACHE_PARENT), "/private/tmp/r46h-build"):
            with self.assertRaises(BUILDER.BuildError):
                BUILDER.safe_cache_root(rejected)

    def test_cargo_seed_rejects_config_aliases_and_unexpected_entries(self) -> None:
        repo = self.root / "cache-repo"
        cargo_home = repo / "mainline/out/.cache/r46h-card-toolchain/cargo-home"
        (cargo_home / "registry").mkdir(parents=True)
        for name in (".global-cache", ".package-cache", ".package-cache-mutate"):
            (cargo_home / name).write_bytes(b"cache\n")
        original = BUILDER.REPO
        BUILDER.REPO = repo
        try:
            destination = self.root / "copied"
            BUILDER.seed_cargo_home(destination)
            self.assertEqual((destination / ".global-cache").read_bytes(), b"cache\n")
            (cargo_home / "CONFIG.TOML").write_text("[build]\n")
            with self.assertRaises(BUILDER.BuildError):
                BUILDER.seed_cargo_home(self.root / "rejected")
        finally:
            BUILDER.REPO = original

    def test_generation_validation_binds_git_manifest_and_binary(self) -> None:
        repo = self.root / "source-repo"
        relative = "mainline/README.md"
        (repo / "mainline").mkdir(parents=True)
        (repo / relative).write_bytes(b"fixture source\n")
        subprocess.run(["git", "init", "-q", repo], check=True)
        subprocess.run(["git", "-C", repo, "config", "user.name", "test"], check=True)
        subprocess.run(
            ["git", "-C", repo, "config", "user.email", "test@example.invalid"],
            check=True,
        )
        subprocess.run(["git", "-C", repo, "add", relative], check=True)
        subprocess.run(["git", "-C", repo, "commit", "-qm", "fixture"], check=True)
        commit = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        tree = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD^{tree}"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()
        blob = subprocess.run(
            ["git", "-C", repo, "cat-file", "blob", f"{commit}:{relative}"],
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        manifest = BUILDER.canonical_json(
            {
                "file_count": 1,
                "files": [
                    {
                        "git_mode": "100644",
                        "path": relative,
                        "sha256": BUILDER.sha256_bytes(blob),
                        "size": len(blob),
                    }
                ],
                "format_version": 1,
                "git_commit": commit,
                "git_tree": tree,
            }
        )
        binary = bytearray(64)
        binary[:6] = b"\x7fELF\x02\x01"
        binary[16:18] = (3).to_bytes(2, "little")
        binary[18:20] = (183).to_bytes(2, "little")
        binary = bytes(binary)
        receipt = BUILDER.canonical_json(
            {
                "artifact": {
                    "name": BUILDER.BINARY_NAME,
                    "sha256": BUILDER.sha256_bytes(binary),
                    "size": len(binary),
                },
                "build": {
                    "built_utc": "2026-08-14T00:00:00Z",
                    "docker_image": BUILDER.DOCKER_IMAGE,
                    "docker_image_id": BUILDER.DOCKER_IMAGE_ID,
                    "reproducible_builds": 2,
                    "rust_packages": [],
                    "source_date_epoch": int(BUILDER.SOURCE_DATE_EPOCH),
                },
                "format_version": 1,
                "runtime_input": {
                    "name": BUILDER.MODULE_PACKAGE.name,
                    "sha256": BUILDER.MODULE_PACKAGE_SHA256,
                    "size": BUILDER.MODULE_PACKAGE_SIZE,
                },
                "source": {
                    "file_count": 1,
                    "git_commit": commit,
                    "git_tree": tree,
                    "manifest_sha256": BUILDER.sha256_bytes(manifest),
                },
            }
        )
        generation = self.root / (
            f"build-{commit[:12]}-{BUILDER.sha256_bytes(binary)[:12]}"
        )
        generation.mkdir()
        members = {
            BUILDER.BINARY_NAME: binary,
            "BUILD-RECEIPT.json": receipt,
            "SOURCE-MANIFEST.json": manifest,
        }
        for name, value in members.items():
            (generation / name).write_bytes(value)
        (generation / "SHA256SUMS").write_text(
            "".join(
                f"{BUILDER.sha256_bytes(value)}  {name}\n"
                for name, value in sorted(members.items())
            )
        )
        original = BUILDER.SOURCE_PATHS
        BUILDER.SOURCE_PATHS = (relative,)
        try:
            BUILDER.validate_generation(generation, commit, repo)
            with (generation / BUILDER.BINARY_NAME).open("ab") as handle:
                handle.write(b"tamper")
            with self.assertRaises(BUILDER.BuildError):
                BUILDER.validate_generation(generation, commit, repo)
        finally:
            BUILDER.SOURCE_PATHS = original

    def test_script_is_syntax_valid_and_source_scope_mentions_all_components(self) -> None:
        compile(SCRIPT.read_text(), str(SCRIPT), "exec")
        expected = {
            "mainline/scripts/build-r46h-v10-target-installer.py",
            "mainline/tests/test-v10-target-installer-build.py",
            "mainline/tools/r46h-v10-target-installer/Cargo.lock",
            "mainline/tools/r46h-v10-target-installer/Cargo.toml",
            "mainline/tools/r46h-v10-target-installer/README.md",
            "mainline/tools/r46h-v10-target-installer/src/lib.rs",
            "mainline/tools/r46h-v10-target-installer/src/linux.rs",
            "mainline/tools/r46h-v10-target-installer/src/main.rs",
        }
        self.assertEqual(set(BUILDER.SOURCE_PATHS), expected)

    def test_runtime_module_package_is_exact_regular_input(self) -> None:
        package = self.root / "module-package.tar.gz"
        package.write_bytes(b"exact-runtime-input\n")
        expected = BUILDER.sha256_file(package)
        self.assertEqual(
            BUILDER.verify_runtime_module_package(package, package.stat().st_size, expected),
            {
                "name": package.name,
                "sha256": expected,
                "size": package.stat().st_size,
            },
        )
        package.write_bytes(b"tampered\n")
        with self.assertRaises(BUILDER.BuildError):
            BUILDER.verify_runtime_module_package(package, 20, expected)


if __name__ == "__main__":
    unittest.main()
