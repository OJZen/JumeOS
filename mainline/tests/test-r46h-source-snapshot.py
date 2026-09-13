#!/usr/bin/env python3
"""Adversarial tests for the canonical R46H build source snapshot."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import Optional
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_BUILD_SCRIPT = REPO_ROOT / "mainline/scripts/build-kernel.sh"
SOURCE_HELPER = REPO_ROOT / "mainline/scripts/r46h-source-snapshot.py"
SOURCE_CLEANUP_SCRIPT = REPO_ROOT / "mainline/scripts/cleanup-stale-build.sh"
TEST_CACHE = REPO_ROOT / "mainline/.cache"
GIT = "/usr/bin/git"
PYTHON = "/usr/bin/python3"
DOCKER = "/Applications/Docker.app/Contents/Resources/bin/docker"
MANIFEST = """\
KERNEL_VERSION=6.12.99
KERNEL_TARBALL=linux-6.12.99.tar.xz
KERNEL_URL=https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.12.99.tar.xz
KERNEL_MIRROR_URL=https://mirrors.ustc.edu.cn/kernel.org/linux/kernel/v6.x/linux-6.12.99.tar.xz
KERNEL_SHA256=6a477222c132033381cda981eb0127f29fbcbba17e820283bc21290f8e408629
KERNEL_LOCALVERSION=-r46h-mainline-fixture
KERNEL_PATCH_LAST=0008
BUILDER_IMAGE=arkos4clone/r46h-kernel-builder:fixture
BUILD_VOLUME_PREFIX=arkos4clone-r46h-fixture
"""


def load_helper():
    spec = importlib.util.spec_from_file_location("r46h_source_snapshot", SOURCE_HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load source snapshot helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_helper()


def run_git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        [GIT, "-C", str(repo), *args],
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def parse_receipt(stdout: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in stdout.decode("utf-8", "strict").splitlines():
        name, value = line.split("=", 1)
        if name in result:
            raise AssertionError(f"duplicate receipt field: {name}")
        result[name] = value
    return result


class FixtureRepository:
    def __init__(self, root: Path) -> None:
        self.repo = root
        self.mainline = root / "mainline"
        self.scripts = self.mainline / "scripts"
        self.cache = self.mainline / ".cache"
        self.board = self.mainline / "board/source.c"
        self.build_script = self.scripts / "build-kernel.sh"
        self.helper = self.scripts / "r46h-source-snapshot.py"
        self.cleanup_script = self.scripts / "cleanup-stale-build.sh"
        self.scripts.mkdir(parents=True)
        self.board.parent.mkdir(parents=True)
        self.cache.mkdir(parents=True)
        shutil.copyfile(SOURCE_BUILD_SCRIPT, self.build_script)
        shutil.copyfile(SOURCE_HELPER, self.helper)
        shutil.copyfile(SOURCE_CLEANUP_SCRIPT, self.cleanup_script)
        self.build_script.chmod(0o755)
        self.helper.chmod(0o755)
        self.cleanup_script.chmod(0o755)
        (self.mainline / "manifest.env").write_text(MANIFEST, encoding="utf-8")
        self.board.write_text("int committed_source;\n", encoding="utf-8")
        (self.mainline / ".gitignore").write_text("/.cache/\n/out/\n", encoding="utf-8")
        run_git(self.repo, "init", "-q")
        run_git(self.repo, "config", "user.email", "fixture@example.invalid")
        run_git(self.repo, "config", "user.name", "R46H Fixture")
        self.commit("fixture baseline")

    @property
    def head(self) -> str:
        return run_git(self.repo, "rev-parse", "HEAD").stdout.decode().strip()

    def commit(self, message: str) -> None:
        run_git(self.repo, "add", "-A")
        run_git(self.repo, "commit", "-q", "-m", message)

    def allocate_snapshot(self) -> tuple[int, Path]:
        path = self.cache / f"r46h-build-input.{secrets.token_hex(12)}"
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        return fd, path

    def create_snapshot(
        self, *, extra_env: dict[str, str] | None = None
    ) -> tuple[subprocess.CompletedProcess, int, Path]:
        fd, path = self.allocate_snapshot()
        initial_identity = MODULE.encode_initial_identity(
            MODULE.initial_file_identity(os.fstat(fd))
        )
        environment = os.environ.copy()
        if extra_env:
            environment.update(extra_env)
        result = subprocess.run(
            [
                PYTHON,
                "-I",
                "-B",
                str(self.helper),
                "create",
                "--repo-root",
                str(self.repo),
                "--running-script",
                str(self.build_script),
                "--snapshot-path",
                str(path),
                "--fd",
                str(fd),
                "--initial-identity",
                initial_identity,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            pass_fds=(fd,),
            timeout=20,
        )
        return result, fd, path


class SourceSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        TEST_CACHE.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(
            prefix="r46h-source-snapshot-test.", dir=TEST_CACHE
        )
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def repository(self, name: str = "repo") -> FixtureRepository:
        path = self.root / name
        path.mkdir()
        return FixtureRepository(path)

    def close_snapshot(self, fd: int, path: Path) -> None:
        os.close(fd)
        if path.exists() or path.is_symlink():
            path.unlink()

    def archive_member(self, fd: int, name: str) -> bytes:
        os.lseek(fd, 0, os.SEEK_SET)
        duplicate = os.dup(fd)
        try:
            with os.fdopen(duplicate, "rb") as handle:
                with tarfile.open(fileobj=handle, mode="r:") as archive:
                    stream = archive.extractfile(name)
                    self.assertIsNotNone(stream)
                    return stream.read()  # type: ignore[union-attr]
        finally:
            os.lseek(fd, 0, os.SEEK_SET)

    def test_baseline_uses_one_anonymous_stable_fd(self) -> None:
        repo = self.repository()
        result, fd, path = repo.create_snapshot()
        try:
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertFalse(path.exists())
            receipt = parse_receipt(result.stdout)
            self.assertEqual(receipt["source_git_commit"], repo.head)
            os.lseek(fd, 0, os.SEEK_SET)
            digest = hashlib.sha256()
            for block in iter(lambda: os.read(fd, 1024 * 1024), b""):
                digest.update(block)
            self.assertEqual(digest.hexdigest(), receipt["source_snapshot_sha256"])
            verify = subprocess.run(
                [
                    PYTHON,
                    "-I",
                    "-B",
                    str(repo.helper),
                    "verify",
                    "--fd",
                    str(fd),
                    "--state",
                    receipt["snapshot_state"],
                    "--sha256",
                    receipt["source_snapshot_sha256"],
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                pass_fds=(fd,),
            )
            self.assertEqual(verify.returncode, 0, verify.stderr.decode())
        finally:
            self.close_snapshot(fd, path)

    def test_path_git_shim_dangerous_environment_and_replace_refs_do_not_leak(self) -> None:
        repo = self.repository()
        commit_a = repo.head
        repo.board.write_text("int replacement_tree_marker;\n", encoding="utf-8")
        repo.commit("replacement tree")
        commit_b = repo.head
        run_git(repo.repo, "checkout", "-q", "--detach", commit_a)
        run_git(repo.repo, "replace", commit_a, commit_b)

        attacker_bin = self.root / "attacker-bin"
        attacker_bin.mkdir()
        marker = self.root / "fake-git-ran"
        fake_git = attacker_bin / "git"
        fake_git.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 97\n", encoding="utf-8")
        fake_git.chmod(0o755)
        result, fd, path = repo.create_snapshot(
            extra_env={
                "PATH": str(attacker_bin),
                "GIT_DIR": str(self.root / "attacker.git"),
                "GIT_WORK_TREE": str(self.root / "attacker-worktree"),
                "GIT_OBJECT_DIRECTORY": str(self.root / "attacker-objects"),
                "GIT_INDEX_FILE": str(self.root / "attacker-index"),
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "tar.tar.command",
                "GIT_CONFIG_VALUE_0": "/usr/bin/false",
                "PYTHONHOME": str(self.root / "attacker-python-home"),
                "PYTHONPATH": str(self.root / "attacker-python-path"),
            }
        )
        try:
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertFalse(marker.exists())
            self.assertEqual(parse_receipt(result.stdout)["source_git_commit"], commit_a)
            payload = self.archive_member(fd, "mainline/board/source.c")
            self.assertNotIn(b"replacement_tree_marker", payload)
            self.assertIn(b"committed_source", payload)
        finally:
            self.close_snapshot(fd, path)

    def test_tar_umask_is_normalized_and_custom_archiver_is_rejected(self) -> None:
        repo = self.repository()
        baseline, baseline_fd, baseline_path = repo.create_snapshot()
        self.assertEqual(baseline.returncode, 0, baseline.stderr.decode())
        baseline_hash = parse_receipt(baseline.stdout)["source_snapshot_sha256"]
        self.close_snapshot(baseline_fd, baseline_path)

        run_git(repo.repo, "config", "tar.umask", "0077")
        normalized, fd, path = repo.create_snapshot()
        try:
            self.assertEqual(normalized.returncode, 0, normalized.stderr.decode())
            self.assertEqual(
                parse_receipt(normalized.stdout)["source_snapshot_sha256"], baseline_hash
            )
        finally:
            self.close_snapshot(fd, path)

        run_git(repo.repo, "config", "tar.tar.command", "/usr/bin/false")
        rejected, fd, path = repo.create_snapshot()
        try:
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn(b"archive-affecting Git configuration", rejected.stderr)
            self.assertFalse(path.exists())
        finally:
            self.close_snapshot(fd, path)

    def test_info_attributes_is_rejected(self) -> None:
        repo = self.repository()
        attributes = repo.repo / ".git/info/attributes"
        attributes.write_text("mainline/board/source.c export-ignore\n", encoding="utf-8")
        result, fd, path = repo.create_snapshot()
        try:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"info/attributes is forbidden", result.stderr)
            self.assertFalse(path.exists())
        finally:
            self.close_snapshot(fd, path)

    def test_assume_unchanged_and_skip_worktree_are_rejected_for_all_inputs(self) -> None:
        cases = (
            ("--assume-unchanged", "mainline/scripts/build-kernel.sh"),
            ("--skip-worktree", "mainline/scripts/r46h-source-snapshot.py"),
            ("--assume-unchanged", "mainline/board/source.c"),
        )
        for index, (option, relative) in enumerate(cases):
            with self.subTest(option=option, relative=relative):
                repo = self.repository(f"masked-{index}")
                target = repo.repo / relative
                run_git(repo.repo, "update-index", option, relative)
                target.write_bytes(target.read_bytes() + b"# hidden drift\n")
                status = run_git(
                    repo.repo, "status", "--porcelain=v1", "--", "mainline"
                ).stdout
                self.assertEqual(status, b"")
                result, fd, path = repo.create_snapshot()
                try:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(b"unsafe index state", result.stderr)
                finally:
                    self.close_snapshot(fd, path)

    def test_committed_export_attributes_and_links_are_rejected(self) -> None:
        attributes_repo = self.repository("attributes")
        (attributes_repo.repo / ".gitattributes").write_text(
            "mainline/board/source.c export-ignore\n", encoding="utf-8"
        )
        attributes_repo.commit("forbidden export attribute")
        result, fd, path = attributes_repo.create_snapshot()
        try:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"export-ignore is forbidden", result.stderr)
        finally:
            self.close_snapshot(fd, path)

        link_repo = self.repository("link")
        link_repo.board.unlink()
        link_repo.board.symlink_to("outside-source.c")
        link_repo.commit("forbidden source link")
        result, fd, path = link_repo.create_snapshot()
        try:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"unsafe committed file mode or link", result.stderr)
        finally:
            self.close_snapshot(fd, path)

    def test_post_archive_recheck_detects_head_index_worktree_and_flag_changes(self) -> None:
        def mutate_head(repo: FixtureRepository) -> None:
            (repo.mainline / "late.c").write_text("int late;\n", encoding="utf-8")
            repo.commit("late head")

        def mutate_index(repo: FixtureRepository) -> None:
            repo.board.write_text("int staged_late;\n", encoding="utf-8")
            run_git(repo.repo, "add", "mainline/board/source.c")

        def mutate_worktree(repo: FixtureRepository) -> None:
            repo.board.write_text("int dirty_late;\n", encoding="utf-8")

        def mutate_flag(repo: FixtureRepository) -> None:
            run_git(
                repo.repo,
                "update-index",
                "--assume-unchanged",
                "mainline/board/source.c",
            )

        cases = (mutate_head, mutate_index, mutate_worktree, mutate_flag)
        for index, mutation in enumerate(cases):
            with self.subTest(mutation=mutation.__name__):
                repo = self.repository(f"late-{index}")
                fd, path = repo.allocate_snapshot()
                initial_identity = MODULE.encode_initial_identity(
                    MODULE.initial_file_identity(os.fstat(fd))
                )
                real_archive = MODULE.archive_to_fd

                def archive_then_mutate(repo_root: Path, head: str, target_fd: int) -> None:
                    real_archive(repo_root, head, target_fd)
                    mutation(repo)

                MODULE.archive_to_fd = archive_then_mutate
                try:
                    with self.assertRaises(MODULE.SnapshotError):
                        MODULE.create_snapshot(
                            repo.repo,
                            repo.build_script,
                            repo.helper,
                            path,
                            fd,
                            initial_identity,
                        )
                finally:
                    MODULE.archive_to_fd = real_archive
                    self.close_snapshot(fd, path)

    def test_archive_nonzero_exit_discards_partial_output_and_drains_stderr(self) -> None:
        repo = self.repository()
        fd, path = repo.allocate_snapshot()
        real_git_command = MODULE.git_command

        def failing_git_command(_repo: Path, _args: list[str]) -> list[str]:
            return [
                PYTHON,
                "-I",
                "-B",
                "-c",
                (
                    "import os,sys; "
                    "os.write(1,b'partial archive'); "
                    "os.write(2,b'x'*131072); "
                    "sys.exit(7)"
                ),
            ]

        MODULE.git_command = failing_git_command
        try:
            with self.assertRaisesRegex(MODULE.SnapshotError, "diagnostics truncated"):
                MODULE.archive_to_fd(repo.repo, repo.head, fd)
            self.assertEqual(os.fstat(fd).st_size, 0)
        finally:
            MODULE.git_command = real_git_command
            self.close_snapshot(fd, path)

    def test_cleanup_refuses_to_unlink_a_competitor(self) -> None:
        repo = self.repository()
        fd, path = repo.allocate_snapshot()
        initial_identity = MODULE.encode_initial_identity(
            MODULE.initial_file_identity(os.fstat(fd))
        )
        displaced = path.with_name(path.name + ".owned")
        path.rename(displaced)
        path.write_bytes(b"competitor\n")
        try:
            with self.assertRaisesRegex(MODULE.SnapshotError, "replaced"):
                MODULE.unlink_owned_snapshot(
                    fd, path, repo.cache, initial_identity
                )
            self.assertEqual(path.read_bytes(), b"competitor\n")
            self.assertTrue(displaced.exists())
        finally:
            os.close(fd)
            path.unlink()
            displaced.unlink()

    def test_mktemp_to_open_replacement_is_not_unlinked_or_truncated(self) -> None:
        repo = self.repository()
        original_fd, path = repo.allocate_snapshot()
        initial_identity = MODULE.encode_initial_identity(
            MODULE.initial_file_identity(os.fstat(original_fd))
        )
        displaced = path.with_name(path.name + ".original")
        os.close(original_fd)
        path.rename(displaced)
        competitor_fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        competitor_payload = b"ordinary competitor must survive\n"
        os.write(competitor_fd, competitor_payload)
        os.lseek(competitor_fd, 0, os.SEEK_SET)
        try:
            with self.assertRaisesRegex(MODULE.SnapshotError, "replaced after mktemp"):
                MODULE.create_snapshot(
                    repo.repo,
                    repo.build_script,
                    repo.helper,
                    path,
                    competitor_fd,
                    initial_identity,
                )
            self.assertEqual(path.read_bytes(), competitor_payload)
            self.assertEqual(os.fstat(competitor_fd).st_size, len(competitor_payload))
            self.assertTrue(displaced.exists())
        finally:
            os.close(competitor_fd)
            path.unlink()
            displaced.unlink()

    def test_verify_rejects_in_place_snapshot_mutation(self) -> None:
        repo = self.repository()
        result, fd, path = repo.create_snapshot()
        try:
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            receipt = parse_receipt(result.stdout)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, b"X")
            verify = subprocess.run(
                [
                    PYTHON,
                    "-I",
                    "-B",
                    str(repo.helper),
                    "verify",
                    "--fd",
                    str(fd),
                    "--state",
                    receipt["snapshot_state"],
                    "--sha256",
                    receipt["source_snapshot_sha256"],
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                pass_fds=(fd,),
            )
            self.assertNotEqual(verify.returncode, 0)
            self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), 0)
        finally:
            self.close_snapshot(fd, path)

    def test_archive_directory_mode_must_be_canonical_0775(self) -> None:
        repo = self.repository()
        result, fd, path = repo.create_snapshot()
        try:
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            os.lseek(fd, 0, os.SEEK_SET)
            source_fd = os.dup(fd)
            members: list[tuple[tarfile.TarInfo, Optional[bytes]]] = []
            with os.fdopen(source_fd, "rb") as handle:
                with tarfile.open(fileobj=handle, mode="r:") as archive:
                    for member in archive:
                        stream = archive.extractfile(member) if member.isreg() else None
                        members.append((member, stream.read() if stream is not None else None))
            rebuilt = io.BytesIO()
            with tarfile.open(fileobj=rebuilt, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for original, payload in members:
                    info = tarfile.TarInfo(original.name)
                    info.type = original.type
                    info.mode = 0o700 if original.name.rstrip("/") == "mainline" else original.mode
                    info.size = len(payload) if payload is not None else 0
                    archive.addfile(info, io.BytesIO(payload) if payload is not None else None)
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, rebuilt.getvalue())
            os.lseek(fd, 0, os.SEEK_SET)
            _, entries, _ = MODULE.parse_tree(repo.repo, repo.head)
            with self.assertRaisesRegex(MODULE.SnapshotError, "directory type or mode"):
                MODULE.validate_archive(fd, entries)
        finally:
            self.close_snapshot(fd, path)

    def test_manifest_bytes_must_use_canonical_lf_records(self) -> None:
        canonical = MANIFEST.encode("utf-8")
        self.assertEqual(MODULE.parse_manifest(canonical)["KERNEL_VERSION"], "6.12.99")
        for malformed in (
            canonical.replace(b"\n", b"\r\n", 1),
            canonical.replace(b"KERNEL_VERSION", b"KERNEL\0_VERSION", 1),
            canonical.rstrip(b"\n"),
            canonical.replace(b"\n", b"\n\n", 1),
        ):
            with self.subTest(malformed=malformed[:48]):
                with self.assertRaises(MODULE.SnapshotError):
                    MODULE.parse_manifest(malformed)

    def test_build_script_streams_the_same_fd_to_both_docker_consumers(self) -> None:
        text = SOURCE_BUILD_SCRIPT.read_text(encoding="utf-8")
        container_text = (
            REPO_ROOT / "mainline/scripts/build-in-container.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn('command -v docker', text)
        self.assertNotIn('command -v git', text)
        self.assertNotIn('--volume "$INPUT_SNAPSHOT:', text)
        self.assertIn('--initial-identity "$SNAPSHOT_INITIAL_IDENTITY"', text)
        self.assertIn('fd-identity --fd "$SNAPSHOT_FD"', text)
        self.assertIn('docker_cmd build "${docker_build_args[@]}" - <&9', text)
        self.assertIn('docker_cmd run --rm -i', text)
        self.assertGreaterEqual(text.count("verify_snapshot_fd"), 5)
        self.assertIn(
            'require_bootstrap_head_executable "$SNAPSHOT_HELPER_RELPATH" "$SNAPSHOT_HELPER"',
            text,
        )
        self.assertLess(text.index("trap cleanup EXIT INT TERM"), text.index('/bin/mkdir -- "$LOCK_DIR"'))
        self.assertNotRegex(text, r"(?m)^\s*docker (?:build|run|volume|info)\b")
        self.assertIn('cp -- "$TARBALL_PATH" "$PRIVATE_TARBALL"', container_text)
        self.assertIn('tar -xJf "$PRIVATE_TARBALL"', container_text)
        self.assertNotIn('tar -xJf "$TARBALL_PATH"', container_text)
        for field in (
            "docker_context",
            "docker_client_version",
            "docker_server_version",
        ):
            self.assertIn(f"printf '{field}=%s", container_text)
        cleanup_text = SOURCE_CLEANUP_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('DOCKER_CONTEXT=desktop-linux', cleanup_text)
        self.assertIn('"$DOCKER_CLI" --context "$DOCKER_CONTEXT"', cleanup_text)
        self.assertNotRegex(cleanup_text, r"(?m)^\s*docker (?:info|volume)\b")
        for script in (SOURCE_BUILD_SCRIPT, SOURCE_CLEANUP_SCRIPT):
            syntax = subprocess.run(
                ["/bin/bash", "-n", str(script)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(syntax.returncode, 0, syntax.stderr.decode())

    @unittest.skipUnless(
        sys.platform == "darwin"
        and Path("/usr/local/bin/docker").is_symlink()
        and Path("/Applications/Docker.app/Contents/Resources/bin/docker").is_file(),
        "requires the fixed macOS Docker Desktop trust boundary",
    )
    def test_build_bootstrap_ignores_path_git_and_docker_shims(self) -> None:
        repo = self.repository("build-bootstrap")
        attacker_bin = self.root / "build-attacker-bin"
        attacker_bin.mkdir()
        git_marker = self.root / "build-fake-git-ran"
        docker_marker = self.root / "build-fake-docker-ran"
        for name, marker in (("git", git_marker), ("docker", docker_marker)):
            executable = attacker_bin / name
            executable.write_text(
                f"#!/bin/sh\ntouch '{marker}'\nexit 97\n", encoding="utf-8"
            )
            executable.chmod(0o755)
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": str(attacker_bin),
                "GIT_DIR": str(self.root / "wrong.git"),
                "DOCKER_HOST": "tcp://127.0.0.1:9",
                "DOCKER_CONTEXT": "attacker",
                "DOCKER_CONFIG": str(self.root / "attacker-docker-config"),
                "DEVELOPER_DIR": str(self.root / "attacker-xcode"),
                "PYTHONHOME": str(self.root / "attacker-python-home"),
                "PYTHONPATH": str(self.root / "attacker-python-path"),
            }
        )
        result = subprocess.run(
            [
                "/bin/bash",
                str(repo.build_script),
                "--build-id",
                "wrong-fixture",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"manifest LOCALVERSION", result.stderr)
        self.assertFalse(git_marker.exists())
        self.assertFalse(docker_marker.exists())
        self.assertFalse((repo.cache / "build.lock").exists())

    @unittest.skipUnless(
        sys.platform == "darwin"
        and Path("/usr/local/bin/docker").is_symlink()
        and Path("/Applications/Docker.app/Contents/Resources/bin/docker").is_file(),
        "requires the fixed macOS Docker Desktop trust boundary",
    )
    def test_existing_build_lock_is_never_cleaned_by_a_failed_acquire(self) -> None:
        repo = self.repository("preexisting-lock")
        lock = repo.cache / "build.lock"
        lock.mkdir()
        sentinel = lock / "pid"
        sentinel.write_text("999999999\n", encoding="ascii")
        result = subprocess.run(
            ["/bin/bash", str(repo.build_script), "--build-id", "wrong-fixture"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("已有 R46H".encode("utf-8"), result.stderr)
        self.assertEqual(sentinel.read_text(encoding="ascii"), "999999999\n")

    def test_volume_receipt_precedes_create_and_cleanup_queries_fail_closed(self) -> None:
        build_source = SOURCE_BUILD_SCRIPT.read_text(encoding="utf-8")
        cleanup_source = SOURCE_CLEANUP_SCRIPT.read_text(encoding="utf-8")

        create_offset = build_source.index("created_volume=$(docker_cmd volume create")
        for required in (
            'WORK_VOLUME="$candidate_volume"',
            'printf \'%s\\n\' "$WORK_VOLUME" > "$LOCK_DIR/volume"',
            'printf \'%s\\n\' "$WORK_VOLUME_REPO_ID" > "$LOCK_DIR/volume-repo"',
            'printf \'%s\\n\' "$WORK_VOLUME_RUN_TOKEN" > "$LOCK_DIR/volume-token"',
        ):
            self.assertLess(build_source.index(required), create_offset)

        self.assertIn(
            "cleanup_volume_list=$(docker_cmd volume ls --format '{{.Name}}'",
            build_source,
        )
        self.assertIn("volume_list_contains", build_source)
        self.assertIn("LOCK_DIR_INODE", build_source)

        self.assertNotIn("done < <(", cleanup_source)
        self.assertIn(
            "all_volumes=$(docker_cmd volume ls --format '{{.Name}}') ||",
            cleanup_source,
        )
        self.assertIn("volume_metadata=$(docker_cmd volume inspect", cleanup_source)
        self.assertIn("lock_volume_token", cleanup_source)
        self.assertIn("lock_dir_inode", cleanup_source)

    @unittest.skipUnless(
        sys.platform == "darwin"
        and Path("/usr/local/bin/docker").is_symlink()
        and Path(DOCKER).is_file(),
        "requires the fixed macOS Docker Desktop trust boundary",
    )
    def test_stale_cleanup_uses_complete_volume_receipt_and_exact_labels(self) -> None:
        def docker(*arguments: str, check: bool = True) -> subprocess.CompletedProcess:
            return subprocess.run(
                [DOCKER, "--context", "desktop-linux", *arguments],
                check=check,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

        def write_lock(repo: FixtureRepository, name: str, token: str, repo_id: str) -> Path:
            lock = repo.cache / "build.lock"
            lock.mkdir()
            (lock / "pid").write_text("999999999\n", encoding="ascii")
            (lock / "volume").write_text(f"{name}\n", encoding="ascii")
            (lock / "volume-repo").write_text(f"{repo_id}\n", encoding="ascii")
            (lock / "volume-token").write_text(f"{token}\n", encoding="ascii")
            return lock

        def run_cleanup(repo: FixtureRepository) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["/bin/bash", str(repo.cleanup_script)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

        docker("info")

        absent_repo = self.repository("cleanup-absent")
        absent_repo_id = hashlib.sha256(str(absent_repo.repo).encode()).hexdigest()[:16]
        absent_token = f"absent-{secrets.token_hex(8)}"
        absent_name = f"arkos4clone-r46h-fixture-cleanup-{absent_token}"
        absent_lock = write_lock(absent_repo, absent_name, absent_token, absent_repo_id)
        absent_result = run_cleanup(absent_repo)
        self.assertEqual(absent_result.returncode, 0, absent_result.stderr.decode())
        self.assertFalse(absent_lock.exists())

        matching_repo = self.repository("cleanup-matching")
        matching_repo_id = hashlib.sha256(str(matching_repo.repo).encode()).hexdigest()[:16]
        matching_token = f"matching-{secrets.token_hex(8)}"
        matching_name = f"arkos4clone-r46h-fixture-cleanup-{matching_token}"
        matching_lock = write_lock(
            matching_repo, matching_name, matching_token, matching_repo_id
        )
        docker(
            "volume",
            "create",
            "--label",
            "org.arkos4clone.r46h.temporary=true",
            "--label",
            f"org.arkos4clone.r46h.repo={matching_repo_id}",
            "--label",
            f"org.arkos4clone.r46h.run-token={matching_token}",
            matching_name,
        )
        try:
            matching_result = run_cleanup(matching_repo)
            self.assertEqual(
                matching_result.returncode, 0, matching_result.stderr.decode()
            )
            self.assertFalse(matching_lock.exists())
            self.assertNotEqual(
                docker("volume", "inspect", matching_name, check=False).returncode, 0
            )
        finally:
            docker("volume", "rm", matching_name, check=False)

        mismatch_repo = self.repository("cleanup-mismatch")
        mismatch_repo_id = hashlib.sha256(str(mismatch_repo.repo).encode()).hexdigest()[:16]
        expected_token = f"expected-{secrets.token_hex(8)}"
        actual_token = f"actual-{secrets.token_hex(8)}"
        mismatch_name = f"arkos4clone-r46h-fixture-cleanup-{expected_token}"
        mismatch_lock = write_lock(
            mismatch_repo, mismatch_name, expected_token, mismatch_repo_id
        )
        docker(
            "volume",
            "create",
            "--label",
            "org.arkos4clone.r46h.temporary=true",
            "--label",
            f"org.arkos4clone.r46h.repo={mismatch_repo_id}",
            "--label",
            f"org.arkos4clone.r46h.run-token={actual_token}",
            mismatch_name,
        )
        try:
            mismatch_result = run_cleanup(mismatch_repo)
            self.assertNotEqual(mismatch_result.returncode, 0)
            self.assertIn(b"run-token", mismatch_result.stderr)
            self.assertTrue(mismatch_lock.exists())
            self.assertEqual(
                docker("volume", "inspect", mismatch_name, check=False).returncode, 0
            )
        finally:
            docker("volume", "rm", mismatch_name, check=False)
            if mismatch_lock.exists():
                shutil.rmtree(mismatch_lock)


if __name__ == "__main__":
    unittest.main(verbosity=2)
