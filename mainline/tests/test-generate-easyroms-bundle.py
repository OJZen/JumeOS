#!/usr/bin/env python3
"""Provenance, canonical-package, and determinism tests for EASYROMS bundles."""

from __future__ import annotations

import copy
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from collections.abc import Callable
from typing import Any


MAINLINE = pathlib.Path(__file__).resolve().parents[1]
REPO = MAINLINE.parent
GENERATOR = MAINLINE / "scripts/generate-easyroms-bundle.py"
CARD = MAINLINE / "deploy/profiles/hl-r46h-v22-g92-v1.json"
NEW_CARD = MAINLINE / "deploy/profiles/hl-r46h-v22-g92-31719424000-v1.json"
BASELINE = MAINLINE / "deploy/baselines/v0.3-eot1.json"
TEMPLATES = MAINLINE / "deploy/templates"
CACHE = MAINLINE / "out/.cache"
BUILD_ID = "v9-fixture"
EPOCH = 1785369600

sys.dont_write_bytecode = True


def load_generator_module(path: pathlib.Path = GENERATOR):
    spec = importlib.util.spec_from_file_location(
        f"r46h_easyroms_generator_{hash(path)}", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load deployment generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR_MODULE = load_generator_module()


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_manifest(root: pathlib.Path) -> list[tuple[str, int, str]]:
    result: list[tuple[str, int, str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            result.append((relative + "/", 0, "directory"))
        else:
            result.append((relative, path.stat().st_mode & 0o777, digest(path)))
    return result


def git(repo: pathlib.Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        GENERATOR_MODULE.git_command(repo, list(args)),
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=GENERATOR_MODULE.clean_git_environment(),
    )


def git_snapshot(repo: pathlib.Path) -> str:
    archive = git(repo, "archive", "--format=tar", "HEAD", "--", "mainline").stdout
    return hashlib.sha256(archive).hexdigest()


ArchiveEntry = dict[str, Any]
ArchiveMutation = Callable[[list[ArchiveEntry], str], None]


def _tree_order(names: set[str], directories: set[str], root: str) -> list[str]:
    children: dict[str, list[str]] = {}
    for name in names - {root}:
        parent = pathlib.PurePosixPath(name).parent.as_posix()
        children.setdefault(parent, []).append(name)
    result = [root]

    def visit(directory: str) -> None:
        for child in sorted(
            children.get(directory, []), key=lambda item: pathlib.PurePosixPath(item).name
        ):
            result.append(child)
            if child in directories:
                visit(child)

    visit(root)
    return result


def build_small_package(
    root: pathlib.Path,
    *,
    build_id: str = BUILD_ID,
    release: str | None = None,
    source_commit: str = "a" * 40,
    source_snapshot: str = "b" * 64,
    tree_hash: str | None = None,
    root_spec: str = "PARTUUID=c9f931c9-02",
    console: str = "ttyS2,115200n8",
    dtb_compatible: str = "rockchip,rk3326-r46h-linux",
    extra_payloads: dict[str, bytes] | None = None,
    mutate: ArchiveMutation | None = None,
    tar_format: int = tarfile.GNU_FORMAT,
) -> pathlib.Path:
    root.mkdir(parents=True, exist_ok=True)
    release = release or f"6.12.99-r46h-mainline-{build_id}"
    package_name = f"r46h-mainline-test-{build_id}"
    module_root = pathlib.PurePosixPath("rootfs/lib/modules") / release
    payloads: dict[str, bytes] = {
        "boot/Image.mainline-test": b"synthetic Image\n",
        "boot/boot.ini.test": b"synthetic boot script\n",
        "boot/rk3326-r46h-mainline-test.dtb": b"synthetic DTB\n",
        f"{module_root}/a.ko": b"ko\n",
        f"{module_root}/b.ko.gz": b"ko.gz\n",
        f"{module_root}/c.ko.xz": b"ko.xz\n",
        f"{module_root}/d.ko.zst": b"ko.zst\n",
        f"{module_root}/modules.dep": b"a.ko:\n",
    }
    payloads.update(extra_payloads or {})
    module_paths = sorted(path for path in payloads if path.startswith(f"{module_root}/"))
    calculated_tree = hashlib.sha256(
        "".join(
            f"{hashlib.sha256(payloads[path]).hexdigest()}  {path}\n"
            for path in module_paths
        ).encode()
    ).hexdigest()
    payloads["MANIFEST"] = (
        "\n".join(
            [
                "format_version=2",
                "target=r46h",
                "soc=rk3326",
                "purpose=mainline-bring-up-test-only",
                f"build_id={build_id}",
                f"kernel_release={release}",
                "kernel_baseline=6.12.99",
                f"dtb_compatible={dtb_compatible}",
                f"root_spec={root_spec}",
                f"console={console}",
                "initramfs=absent",
                "module_count=4",
                f"module_tree_sha256={tree_hash or calculated_tree}",
                f"source_git_commit={source_commit}",
                f"source_snapshot_sha256={source_snapshot}",
                "created_utc=2026-07-30T00:00:00Z",
                "image_file=boot/Image.mainline-test",
                "dtb_file=boot/rk3326-r46h-mainline-test.dtb",
                "boot_script=boot/boot.ini.test",
                f"modules_path={module_root}",
                "",
            ]
        ).encode()
    )
    sums = "".join(
        f"{hashlib.sha256(payloads[path]).hexdigest()}  {path}\n"
        for path in sorted(payloads)
    ).encode()
    payloads["SHA256SUMS"] = sums

    file_names = {f"{package_name}/{relative}" for relative in payloads}
    directory_names = {package_name}
    for name in file_names:
        parent = pathlib.PurePosixPath(name).parent
        while parent.as_posix() != ".":
            directory_names.add(parent.as_posix())
            parent = parent.parent
    all_names = file_names | directory_names
    entries: list[ArchiveEntry] = []
    for name in _tree_order(all_names, directory_names, package_name):
        relative = name[len(package_name) + 1 :] if name != package_name else ""
        is_directory = name in directory_names
        entries.append(
            {
                "name": name,
                "type": tarfile.DIRTYPE if is_directory else tarfile.REGTYPE,
                "mode": 0o755 if is_directory else 0o644,
                "uid": 0,
                "gid": 0,
                "uname": "",
                "gname": "",
                "linkname": "",
                "data": b"" if is_directory else payloads[relative],
                "pax_headers": {},
            }
        )
    if mutate is not None:
        mutate(entries, package_name)

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tar_format) as archive:
        for entry in entries:
            info = tarfile.TarInfo(entry["name"])
            info.type = entry["type"]
            info.mode = entry["mode"]
            info.uid = entry["uid"]
            info.gid = entry["gid"]
            info.uname = entry["uname"]
            info.gname = entry["gname"]
            info.linkname = entry["linkname"]
            info.mtime = EPOCH
            info.pax_headers = entry["pax_headers"]
            data = entry["data"]
            info.size = len(data) if info.type in {tarfile.REGTYPE, tarfile.AREGTYPE} else 0
            archive.addfile(info, io.BytesIO(data) if info.size else None)
    archive_path = root / f"{package_name}.tar.gz"
    archive_path.write_bytes(gzip_bytes(raw.getvalue()))
    return archive_path


def mutate_member(suffix: str, **changes: Any) -> ArchiveMutation:
    def mutate(entries: list[ArchiveEntry], package_name: str) -> None:
        target = f"{package_name}/{suffix}"
        entry = next(item for item in entries if item["name"] == target)
        entry.update(changes)

    return mutate


def gzip_bytes(raw: bytes) -> bytes:
    result = io.BytesIO()
    with gzip.GzipFile(
        filename="", mode="wb", compresslevel=9, fileobj=result, mtime=0
    ) as compressed:
        compressed.write(raw)
    canonical = bytearray(result.getvalue())
    canonical[9] = 3  # GNU gzip on the Linux canonical builder records Unix.
    return bytes(canonical)


def rewrite_raw_archive(
    source: pathlib.Path,
    destination_root: pathlib.Path,
    transform: Callable[[bytes], bytes],
) -> pathlib.Path:
    destination_root.mkdir(parents=True, exist_ok=True)
    destination = destination_root / source.name
    destination.write_bytes(gzip_bytes(transform(gzip.decompress(source.read_bytes()))))
    return destination


def tar_extension_record(entry_type: bytes, payload: bytes) -> bytes:
    info = tarfile.TarInfo("././@LongLink")
    info.type = entry_type
    info.mode = 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    info.size = len(payload)
    header = info.tobuf(format=tarfile.GNU_FORMAT)
    padding = b"\0" * ((-len(payload)) % 512)
    return header + payload + padding


def replace_tar_header_field(
    raw: bytes, offset: int, field: slice, replacement: bytes
) -> bytes:
    changed = bytearray(raw)
    header = bytearray(changed[offset : offset + 512])
    header[field] = replacement
    header[148:156] = b"        "
    checksum = sum(header)
    header[148:156] = f"{checksum:06o}".encode() + b"\0 "
    changed[offset : offset + 512] = header
    return bytes(changed)


class HermeticRepository:
    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.repo = root / "repo"
        self.mainline = self.repo / "mainline"
        (self.mainline / "scripts").mkdir(parents=True)
        (self.mainline / "deploy/profiles").mkdir(parents=True)
        (self.mainline / "deploy/baselines").mkdir(parents=True)
        (self.mainline / "deploy/templates").mkdir(parents=True)
        shutil.copy2(GENERATOR, self.mainline / "scripts/generate-easyroms-bundle.py")
        shutil.copy2(CARD, self.mainline / "deploy/profiles/hl-r46h-v22-g92-v1.json")
        shutil.copy2(
            NEW_CARD,
            self.mainline / "deploy/profiles/hl-r46h-v22-g92-31719424000-v1.json",
        )
        shutil.copy2(BASELINE, self.mainline / "deploy/baselines/v0.3-eot1.json")
        for template in TEMPLATES.iterdir():
            if template.is_file():
                shutil.copy2(template, self.mainline / "deploy/templates" / template.name)
        shutil.copy2(MAINLINE / ".gitignore", self.mainline / ".gitignore")
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "R46H Fixture")
        git(self.repo, "config", "user.email", "r46h-fixture@example.invalid")
        self.commit("fixture source")

    @property
    def generator(self) -> pathlib.Path:
        return self.mainline / "scripts/generate-easyroms-bundle.py"

    @property
    def card(self) -> pathlib.Path:
        return self.mainline / "deploy/profiles/hl-r46h-v22-g92-v1.json"

    @property
    def new_card(self) -> pathlib.Path:
        return self.mainline / "deploy/profiles/hl-r46h-v22-g92-31719424000-v1.json"

    @property
    def baseline(self) -> pathlib.Path:
        return self.mainline / "deploy/baselines/v0.3-eot1.json"

    @property
    def head(self) -> str:
        return git(self.repo, "rev-parse", "HEAD").stdout.decode().strip()

    @property
    def snapshot(self) -> str:
        return git_snapshot(self.repo)

    def commit(self, message: str) -> None:
        git(self.repo, "add", "mainline")
        environment = os.environ.copy()
        environment.update(
            {
                "LC_ALL": "C",
                "LANG": "C",
                "GIT_AUTHOR_DATE": "2026-07-30T00:00:00Z",
                "GIT_COMMITTER_DATE": "2026-07-30T00:00:00Z",
            }
        )
        subprocess.run(
            ["git", "-C", str(self.repo), "commit", "-q", "-m", message],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        )

    def package(self, root: pathlib.Path, **kwargs: Any) -> pathlib.Path:
        return build_small_package(
            root,
            source_commit=self.head,
            source_snapshot=self.snapshot,
            **kwargs,
        )

    def run_generator(
        self,
        package: pathlib.Path,
        output: pathlib.Path,
        *,
        card: pathlib.Path | None = None,
        baseline: pathlib.Path | None = None,
        action_policy: str = "full",
        epoch: int = EPOCH,
        extra_env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> subprocess.CompletedProcess[str]:
        output.mkdir(parents=True, exist_ok=True)
        return subprocess.run(
            [
                sys.executable,
                str(self.generator),
                "--package-tar",
                str(package),
                "--card-profile",
                str(card or self.card),
                "--current-baseline",
                str(baseline or self.baseline),
                "--purpose",
                "synthetic-generator-fixture",
                "--action-policy",
                action_policy,
                "--source-date-epoch",
                str(epoch),
                "--output-dir",
                str(output),
            ],
            cwd=self.repo,
            check=False,
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                **(extra_env or {}),
            },
            timeout=timeout,
        )


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        CACHE.mkdir(parents=True, exist_ok=True)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix=".easyroms-generator-test.", dir=CACHE
        )
        self.root = pathlib.Path(self.temporary.name)
        self.source = HermeticRepository(self.root / "source")
        self.package = self.source.package(self.root / "input")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def generate(self, output: pathlib.Path) -> subprocess.CompletedProcess[str]:
        return self.source.run_generator(self.package, output)

    def test_two_generations_are_byte_identical(self) -> None:
        first = self.root / "first"
        second = self.root / "second"
        one = self.generate(first)
        two = self.generate(second)
        self.assertEqual(one.returncode, 0, one.stderr)
        self.assertEqual(two.returncode, 0, two.stderr)
        one_dir = first / f"r46h-easyroms-{BUILD_ID}"
        two_dir = second / f"r46h-easyroms-{BUILD_ID}"
        self.assertEqual(one_dir.stat().st_mode & 0o777, 0o755)
        self.assertEqual(two_dir.stat().st_mode & 0o777, 0o755)
        self.assertEqual(tree_manifest(one_dir), tree_manifest(two_dir))
        self.assertEqual(
            digest(first / f"r46h-easyroms-{BUILD_ID}.tar.gz"),
            digest(second / f"r46h-easyroms-{BUILD_ID}.tar.gz"),
        )
        for output in (first, second):
            self.assertEqual(
                [path.name for path in output.iterdir() if path.name.startswith(".easyroms-")],
                [],
            )

    def test_new_card_profile_generates_with_its_pinned_identity(self) -> None:
        output = self.root / "new-card-output"
        result = self.source.run_generator(
            self.package,
            output,
            card=self.source.new_card,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = output / f"r46h-easyroms-{BUILD_ID}" / "payload"
        manifest = (payload / "DEPLOY-MANIFEST").read_text(encoding="utf-8")
        self.assertIn(
            "card_profile_id=hl-r46h-v22-g92-31719424000-v1\n",
            manifest,
        )
        self.assertIn(
            f"card_profile_sha256={digest(self.source.new_card)}\n",
            manifest,
        )
        self.assertIn("card_whole_size=31719424000\n", manifest)
        self.assertIn("card_easyroms_size=20868328960\n", manifest)
        self.assertIn(
            "card_easyroms_uuid=E1F5295C-4B12-A54A-ACB7-317194240001\n",
            manifest,
        )
        self.assertIn(
            "card_g92_prefix_sha256="
            "97ede10075b3257c638a04b3044c9dda2d8dd9adc6f6fee3be7b004a31fb135e\n",
            manifest,
        )

    def test_generated_bundle_has_exact_source_list_and_valid_shell(self) -> None:
        output = self.root / "output"
        result = self.generate(output)
        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = output / f"r46h-easyroms-{BUILD_ID}"
        payload = bundle / "payload"
        listed: list[tuple[str, str]] = []
        for line in (bundle / "STAGE-SOURCES.sha256").read_text().splitlines():
            expected, relative = line.split("  ", 1)
            listed.append((relative, expected))
        self.assertEqual(
            [relative for relative, _ in listed],
            sorted(relative for relative, _ in listed),
        )
        self.assertEqual(len(listed), len({relative for relative, _ in listed}))
        actual = sorted(
            (f"payload/{path.name}", digest(path))
            for path in payload.iterdir()
            if path.is_file()
        )
        self.assertEqual(listed, actual)
        for script in (
            bundle / "stage-on-macos.sh",
            payload / "bootstrap-target.sh",
            payload / "target-common.sh",
            payload / "install-modules.sh",
            payload / "switch-boot.sh",
        ):
            subprocess.run(["bash", "-n", str(script)], check=True)
        stage_script = (bundle / "stage-on-macos.sh").read_text()
        self.assertIn('if ! actual_size=$(target_size "$path"); then', stage_script)
        self.assertIn('cannot read ${label} size: ${path}', stage_script)
        self.assertIn('if ! actual_hash=$(target_hash "$path"); then', stage_script)
        self.assertIn('cannot read ${label} SHA-256: ${path}', stage_script)
        self.assertIn('fixed ${roms_partition} payload writes', stage_script)
        self.assertNotIn('fixed disk4s3 payload writes', stage_script)
        disabled_message = (
            "physical EASYROMS file staging is disabled pending raw exFAT "
            "verification"
        )
        self.assertIn(disabled_message, stage_script)
        self.assertLess(
            stage_script.index(disabled_message),
            stage_script.index('card_identity_matches || fail "$device is not the audited R46H card"'),
        )
        manifest = (payload / "DEPLOY-MANIFEST").read_text()
        self.assertIn("format_version=3\n", manifest)
        self.assertIn("action_policy=full\n", manifest)
        self.assertIn("allowed_actions=install-modules,switch-boot\n", manifest)
        self.assertIn(f"source_git_commit={self.source.head}\n", manifest)
        self.assertIn(f"source_snapshot_sha256={self.source.snapshot}\n", manifest)
        self.assertIn("current_baseline_id=v0.3-eot1\n", manifest)
        self.assertIn("fallback_release=6.12.99-r46h-mainline-v0.2\n", manifest)

    def test_install_modules_only_bundle_omits_and_rejects_boot_switch(self) -> None:
        output = self.root / "modules-only-output"
        result = self.source.run_generator(
            self.package,
            output,
            card=self.source.new_card,
            action_policy="install-modules-only",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = output / f"r46h-easyroms-{BUILD_ID}"
        payload = bundle / "payload"
        self.assertFalse((payload / "switch-boot.sh").exists())
        manifest = (payload / "DEPLOY-MANIFEST").read_text(encoding="utf-8")
        self.assertIn("action_policy=install-modules-only\n", manifest)
        self.assertIn("allowed_actions=install-modules\n", manifest)
        self.assertIn("target_boot_switch=disabled\n", manifest)
        source_list = (bundle / "STAGE-SOURCES.sha256").read_text(encoding="utf-8")
        self.assertNotIn("payload/switch-boot.sh", source_list)
        bootstrap = (payload / "bootstrap-target.sh").read_text(encoding="utf-8")
        self.assertIn("requested action is not authorized by the external receipt", bootstrap)
        self.assertIn("modules-only source list contains switch-boot.sh", bootstrap)
        stage = (bundle / "stage-on-macos.sh").read_text(encoding="utf-8")
        self.assertIn("modules-only source unexpectedly contains switch-boot.sh", stage)
        for script in (
            bundle / "stage-on-macos.sh",
            payload / "bootstrap-target.sh",
            payload / "target-common.sh",
            payload / "install-modules.sh",
        ):
            subprocess.run(["bash", "-n", str(script)], check=True)

    @unittest.skipUnless(
        os.environ.get("R46H_RUN_MODULES_ONLY_TARGET_INTEGRATION") == "1",
        "set R46H_RUN_MODULES_ONLY_TARGET_INTEGRATION=1 inside the builder container",
    )
    def test_modules_only_receipt_rejects_switch_before_target_mutation(self) -> None:
        if os.geteuid() != 0 or not pathlib.Path("/.dockerenv").is_file():
            self.skipTest("target bootstrap integration is root/container-only")

        output = self.root / "modules-only-target-output"
        result = self.source.run_generator(
            self.package,
            output,
            card=self.source.new_card,
            action_policy="install-modules-only",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = output / f"r46h-easyroms-{BUILD_ID}" / "payload"

        target_root = pathlib.Path(
            tempfile.mkdtemp(prefix=".r46h-target-test.", dir=CACHE)
        )
        target_root.chmod(0o700)
        self.addCleanup(shutil.rmtree, target_root)
        trusted = target_root / "run/r46h-deploy"
        trusted.mkdir(parents=True, mode=0o700)
        bootstrap = trusted / "bootstrap-target.sh"
        shutil.copyfile(payload / "bootstrap-target.sh", bootstrap)
        bootstrap.chmod(0o700)
        bootstrap_sha = digest(bootstrap)
        receipt = trusted / "TARGET-TRUST-RECEIPT"
        receipt.write_text(
            "\n".join(
                [
                    "format_version=1",
                    "status=complete",
                    "target=HL-R46H-V22",
                    f"payload=r46h-{BUILD_ID}",
                    f"kernel_release=6.12.99-r46h-mainline-{BUILD_ID}",
                    "allowed_actions=install-modules",
                    f"card_profile_sha256={digest(self.source.new_card)}",
                    f"stage_complete_sha256={'1' * 64}",
                    f"bootstrap_target_sha256={bootstrap_sha}",
                    f"stage_sources_sha256={'2' * 64}",
                    f"completion_secret={'3' * 64}",
                    f"completion_secret_sha256={'4' * 64}",
                    f"g92_prefix_sha256={'5' * 64}",
                    f"boot_partition_sha256={'6' * 64}",
                    "only_written_partition=3",
                    "root_partition=never-mounted",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        receipt.chmod(0o600)
        receipt_sha = digest(receipt)
        sentinel = target_root / "no-target-mutation"
        sentinel.write_text("unchanged\n", encoding="utf-8")
        before = tree_manifest(target_root)

        attempted = subprocess.run(
            [
                "bash",
                str(bootstrap),
                "--external-receipt",
                str(receipt),
                "--external-receipt-sha256",
                receipt_sha,
                "--action",
                "switch-boot",
            ],
            check=False,
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "R46H_DEPLOY_TARGET_TEST_ROOT": str(target_root),
            },
        )
        self.assertNotEqual(attempted.returncode, 0)
        self.assertIn(
            "requested action is not authorized by the external receipt",
            attempted.stderr,
        )
        self.assertEqual(tree_manifest(target_root), before)

    def test_refuses_to_overwrite_or_publish_around_existing_paths(self) -> None:
        output = self.root / "output"
        self.assertEqual(self.generate(output).returncode, 0)
        second = self.generate(output)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("already exists", second.stderr)

        linked = self.root / "linked"
        linked.mkdir()
        (linked / f"r46h-easyroms-{BUILD_ID}").symlink_to(linked / "missing")
        result = self.generate(linked)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists", result.stderr)

        root_link = self.root / "root-output-link"
        root_link.symlink_to(pathlib.Path("/"), target_is_directory=True)
        result = self.generate(root_link)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe resolved output directory", result.stderr)

    def test_binds_package_to_clean_head_and_git_archive(self) -> None:
        dirty_template = self.source.mainline / "deploy/templates/boot.ini.in"
        dirty_template.write_bytes(dirty_template.read_bytes() + b"# dirty\n")
        dirty = self.generate(self.root / "dirty-output")
        self.assertNotEqual(dirty.returncode, 0)
        self.assertIn("mainline worktree must be completely clean", dirty.stderr)
        git(self.source.repo, "restore", "mainline/deploy/templates/boot.ini.in")

        wrong_commit = build_small_package(
            self.root / "wrong-commit",
            source_commit="f" * 40,
            source_snapshot=self.source.snapshot,
        )
        result = self.source.run_generator(wrong_commit, self.root / "wrong-commit-output")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source commit does not match source HEAD", result.stderr)

        wrong_snapshot = build_small_package(
            self.root / "wrong-snapshot",
            source_commit=self.source.head,
            source_snapshot="e" * 64,
        )
        result = self.source.run_generator(wrong_snapshot, self.root / "wrong-snapshot-output")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source snapshot does not match git archive", result.stderr)

        (self.source.mainline / "ADVANCED").write_text("new commit\n")
        self.source.commit("advance source")
        advanced = self.generate(self.root / "advanced-output")
        self.assertNotEqual(advanced.returncode, 0)
        self.assertIn("source commit does not match source HEAD", advanced.stderr)

    def test_git_replace_and_dangerous_environment_cannot_redirect_head(self) -> None:
        commit_a = self.source.head
        snapshot_a = self.source.snapshot
        replacement_template = self.source.mainline / "deploy/templates/boot.ini.in"
        replacement_template.write_bytes(
            replacement_template.read_bytes() + b"# REPLACEMENT-B-MUST-NOT-LEAK\n"
        )
        self.source.commit("replacement tree B")
        commit_b = self.source.head
        git(self.source.repo, "checkout", "-q", "--detach", commit_a)
        git(self.source.repo, "replace", commit_a, commit_b)
        package = build_small_package(
            self.root / "replace-package",
            source_commit=commit_a,
            source_snapshot=snapshot_a,
        )
        attacker_bin = self.root / "attacker-bin"
        attacker_bin.mkdir()
        fake_git = attacker_bin / "git"
        fake_git.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
        fake_git.chmod(0o755)
        output = self.root / "replace-output"
        result = self.source.run_generator(
            package,
            output,
            extra_env={
                "PATH": str(attacker_bin),
                "GIT_DIR": str(self.root / "attacker.git"),
                "GIT_WORK_TREE": str(self.root / "attacker-worktree"),
                "GIT_OBJECT_DIRECTORY": str(self.root / "attacker-objects"),
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = output / f"r46h-easyroms-{BUILD_ID}/payload"
        self.assertNotIn(
            "REPLACEMENT-B-MUST-NOT-LEAK",
            (payload / f"boot.ini.{BUILD_ID}").read_text(),
        )
        self.assertIn(
            f"source_git_commit={commit_a}\n",
            (payload / "DEPLOY-MANIFEST").read_text(),
        )

    def test_git_archive_drains_large_stderr_without_deadlock(self) -> None:
        source = HermeticRepository(self.root / "archive-stderr-source")
        attributes = source.mainline / ".gitattributes"
        attributes.write_text("!bad attr\n" * 20_000, encoding="utf-8")
        source.commit("large deterministic archive diagnostics")
        package = source.package(self.root / "archive-stderr-package")
        result = source.run_generator(
            package,
            self.root / "archive-stderr-output",
            timeout=15.0,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])

    def test_git_archive_normalizes_umask_and_rejects_local_archive_inputs(self) -> None:
        normalized = HermeticRepository(self.root / "normalized-archive-source")
        snapshot = normalized.snapshot
        git(normalized.repo, "config", "--local", "tar.umask", "0077")
        self.assertEqual(normalized.snapshot, snapshot)
        package = normalized.package(self.root / "normalized-archive-package")
        result = normalized.run_generator(
            package, self.root / "normalized-archive-output"
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        attributes_source = HermeticRepository(self.root / "info-attributes-source")
        package = attributes_source.package(self.root / "info-attributes-package")
        info_attributes = attributes_source.repo / ".git/info/attributes"
        info_attributes.write_text(
            "mainline/deploy/templates/boot.ini.in export-ignore\n",
            encoding="utf-8",
        )
        result = attributes_source.run_generator(
            package, self.root / "info-attributes-output"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("info/attributes is forbidden", result.stderr)

        custom_archiver = HermeticRepository(self.root / "custom-archiver-source")
        package = custom_archiver.package(self.root / "custom-archiver-package")
        git(
            custom_archiver.repo,
            "config",
            "--local",
            "tar.tar.command",
            "/usr/bin/false",
        )
        result = custom_archiver.run_generator(
            package, self.root / "custom-archiver-output"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("archive-affecting Git configuration is forbidden", result.stderr)

        included_archiver = HermeticRepository(self.root / "included-archiver-source")
        package = included_archiver.package(self.root / "included-archiver-package")
        included_config = self.root / "archive-include.config"
        included_config.write_text(
            '[tar "tar"]\n\tcommand = /usr/bin/false\n', encoding="utf-8"
        )
        git(
            included_archiver.repo,
            "config",
            "--local",
            "include.path",
            str(included_config),
        )
        result = included_archiver.run_generator(
            package, self.root / "included-archiver-output"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("archive-affecting Git configuration is forbidden", result.stderr)

    def test_rejects_index_masking_and_running_generator_byte_drift(self) -> None:
        for option in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(option=option):
                source = HermeticRepository(
                    self.root / option.removeprefix("--").replace("-", "_")
                )
                package = source.package(self.root / f"package-{option.removeprefix('--')}")
                committed_generator = source.generator.read_bytes()
                git(
                    source.repo,
                    "update-index",
                    option,
                    "mainline/scripts/generate-easyroms-bundle.py",
                )
                source.generator.write_bytes(
                    committed_generator + b"\n# masked generator drift\n"
                )
                status = git(
                    source.repo,
                    "status",
                    "--porcelain=v1",
                    "--",
                    "mainline",
                ).stdout
                self.assertEqual(status, b"", status)
                result = source.run_generator(
                    package,
                    self.root / f"masked-output-{option.removeprefix('--')}",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unsafe index state", result.stderr)
                module = load_generator_module(source.generator)
                with self.assertRaisesRegex(module.BundleError, "do not match its exact HEAD blob"):
                    module.require_running_generator_matches_head(
                        source.generator, committed_generator
                    )

        for option in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(option=option, path="mainline/board/source.c"):
                source = HermeticRepository(
                    self.root / f"board_{option.removeprefix('--').replace('-', '_')}"
                )
                board_source = source.mainline / "board/source.c"
                board_source.parent.mkdir()
                board_source.write_text("int committed_source;\n", encoding="utf-8")
                source.commit("add non-generator source")
                package = source.package(
                    self.root / f"board-package-{option.removeprefix('--')}"
                )
                git(
                    source.repo,
                    "update-index",
                    option,
                    "mainline/board/source.c",
                )
                board_source.write_text("int hidden_dirty_source;\n", encoding="utf-8")
                status = git(
                    source.repo,
                    "status",
                    "--porcelain=v1",
                    "--",
                    "mainline",
                ).stdout
                self.assertEqual(status, b"", status)
                result = source.run_generator(
                    package,
                    self.root / f"board-masked-output-{option.removeprefix('--')}",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unsafe index state", result.stderr)

    def test_all_committed_inputs_require_exact_regular_git_modes(self) -> None:
        template_source = HermeticRepository(self.root / "template-mode-source")
        template = template_source.mainline / "deploy/templates/boot.ini.in"
        template.unlink()
        template.symlink_to("attacker-template")
        template_source.commit("template symlink")
        package = template_source.package(self.root / "template-mode-package")
        result = template_source.run_generator(
            package, self.root / "template-mode-output"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mode/type mismatch", result.stderr)

        generator_source = HermeticRepository(self.root / "generator-mode-source")
        generator_source.generator.chmod(0o644)
        generator_source.commit("non-executable generator")
        package = generator_source.package(self.root / "generator-mode-package")
        result = generator_source.run_generator(
            package, self.root / "generator-mode-output"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mode/type mismatch", result.stderr)

        profile_source = HermeticRepository(self.root / "profile-mode-source")
        profile_source.card.chmod(0o755)
        profile_source.commit("executable profile")
        package = profile_source.package(self.root / "profile-mode-package")
        result = profile_source.run_generator(
            package, self.root / "profile-mode-output"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mode/type mismatch", result.stderr)

    def test_atomic_publication_never_overwrites_or_deletes_competitors(self) -> None:
        module = load_generator_module(self.source.generator)

        def arguments(output: pathlib.Path) -> argparse.Namespace:
            return argparse.Namespace(
                package_tar=str(self.package),
                card_profile=str(self.source.card),
                current_baseline=str(self.source.baseline),
                purpose="synthetic-generator-fixture",
                source_date_epoch=EPOCH,
                output_dir=str(output),
            )

        real_rename = module.rename_noreplace_at
        directory_output = self.root / "directory-race-output"
        directory_output.mkdir()

        def race_directory(
            source_fd: int, source_name: str, destination_fd: int, destination_name: str
        ) -> None:
            os.mkdir(destination_name, 0o755, dir_fd=destination_fd)
            competitor_fd = os.open(
                destination_name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                dir_fd=destination_fd,
            )
            try:
                marker_fd = os.open(
                    "COMPETITOR",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=competitor_fd,
                )
                os.write(marker_fd, b"directory competitor\n")
                os.close(marker_fd)
            finally:
                os.close(competitor_fd)
            real_rename(source_fd, source_name, destination_fd, destination_name)

        module.rename_noreplace_at = race_directory
        try:
            with self.assertRaisesRegex(module.BundleError, "appeared during atomic publication"):
                module.build_bundle(arguments(directory_output))
        finally:
            module.rename_noreplace_at = real_rename
        competitor_dir = directory_output / f"r46h-easyroms-{BUILD_ID}"
        self.assertEqual(
            (competitor_dir / "COMPETITOR").read_bytes(), b"directory competitor\n"
        )

        archive_output = self.root / "archive-race-output"
        archive_output.mkdir()
        calls = 0

        def race_archive(
            source_fd: int, source_name: str, destination_fd: int, destination_name: str
        ) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                competitor_fd = os.open(
                    destination_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=destination_fd,
                )
                os.write(competitor_fd, b"archive competitor\n")
                os.close(competitor_fd)
            real_rename(source_fd, source_name, destination_fd, destination_name)

        module.rename_noreplace_at = race_archive
        try:
            with self.assertRaisesRegex(module.BundleError, "retained") as raised:
                module.build_bundle(arguments(archive_output))
        finally:
            module.rename_noreplace_at = real_rename
        self.assertEqual(
            (archive_output / f"r46h-easyroms-{BUILD_ID}.tar.gz").read_bytes(),
            b"archive competitor\n",
        )
        self.assertTrue((archive_output / f"r46h-easyroms-{BUILD_ID}").is_dir())
        retained_archives = list(archive_output.glob(".easyroms-archive.*.tar.gz"))
        self.assertEqual(len(retained_archives), 1, retained_archives)
        self.assertIn(retained_archives[0].name, str(raised.exception))

    def test_private_stage_path_swap_is_rejected_without_deleting_competitor(self) -> None:
        module = load_generator_module(self.source.generator)
        output = self.root / "staging-root-race-output"
        output.mkdir()
        real_archive = module.deterministic_archive_at
        swapped: dict[str, pathlib.Path] = {}

        def swap_after_archive(
            source_fd: int,
            source_name: str,
            archive_parent_fd: int,
            archive_name: str,
            epoch: int,
        ) -> tuple[int, tuple[int, int]]:
            archive_result = real_archive(
                source_fd,
                source_name,
                archive_parent_fd,
                archive_name,
                epoch,
            )
            candidates = list(output.glob(".easyroms-bundle.*"))
            self.assertEqual(len(candidates), 1, candidates)
            original_name = candidates[0]
            displaced = output / ".displaced-owned-temp"
            original_name.rename(displaced)
            original_name.mkdir()
            (original_name / "COMPETITOR").write_bytes(b"must survive failure\n")
            swapped.update(competitor=original_name, displaced=displaced)
            return archive_result

        module.deterministic_archive_at = swap_after_archive
        try:
            with self.assertRaisesRegex(
                module.BundleError, "private directory source identity changed"
            ):
                module.build_bundle(
                    argparse.Namespace(
                        package_tar=str(self.package),
                        card_profile=str(self.source.card),
                        current_baseline=str(self.source.baseline),
                        purpose="synthetic-generator-fixture",
                        source_date_epoch=EPOCH,
                        output_dir=str(output),
                    )
                )
        finally:
            module.deterministic_archive_at = real_archive
        self.assertEqual(
            (swapped["competitor"] / "COMPETITOR").read_bytes(),
            b"must survive failure\n",
        )
        self.assertTrue(swapped["displaced"].is_dir())
        self.assertFalse((output / f"r46h-easyroms-{BUILD_ID}").exists())
        self.assertFalse((output / f"r46h-easyroms-{BUILD_ID}.tar.gz").exists())

    def test_private_stage_and_archive_entry_swaps_are_rejected(self) -> None:
        for target in ("stage", "archive"):
            with self.subTest(target=target):
                module = load_generator_module(self.source.generator)
                output = self.root / f"private-entry-race-{target}"
                output.mkdir()
                real_archive = module.deterministic_archive_at

                def swap_private_entry(
                    source_fd: int,
                    source_name: str,
                    archive_parent_fd: int,
                    archive_name: str,
                    epoch: int,
                ) -> tuple[int, tuple[int, int]]:
                    archive_result = real_archive(
                        source_fd,
                        source_name,
                        archive_parent_fd,
                        archive_name,
                        epoch,
                    )
                    if target == "stage":
                        candidates = list(output.glob(".easyroms-bundle.*"))
                        self.assertEqual(len(candidates), 1, candidates)
                        selected = candidates[0].name
                    else:
                        selected = archive_name
                    displaced = f"{selected}.owned-displaced"
                    os.rename(
                        selected,
                        displaced,
                        src_dir_fd=archive_parent_fd,
                        dst_dir_fd=archive_parent_fd,
                    )
                    if target == "stage":
                        os.mkdir(selected, 0o700, dir_fd=archive_parent_fd)
                    else:
                        attacker_fd = os.open(
                            selected,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                            0o600,
                            dir_fd=archive_parent_fd,
                        )
                        os.write(attacker_fd, b"ATTACKER-ARCHIVE\n")
                        os.close(attacker_fd)
                    return archive_result

                module.deterministic_archive_at = swap_private_entry
                try:
                    with self.assertRaisesRegex(
                        module.BundleError,
                        rf"private {'directory' if target == 'stage' else 'file'} source identity changed",
                    ):
                        module.build_bundle(
                            argparse.Namespace(
                                package_tar=str(self.package),
                                card_profile=str(self.source.card),
                                current_baseline=str(self.source.baseline),
                                purpose="synthetic-generator-fixture",
                                source_date_epoch=EPOCH,
                                output_dir=str(output),
                            )
                        )
                finally:
                    module.deterministic_archive_at = real_archive
                self.assertFalse((output / f"r46h-easyroms-{BUILD_ID}").exists())
                self.assertFalse(
                    (output / f"r46h-easyroms-{BUILD_ID}.tar.gz").exists()
                )

    def test_private_directory_open_failure_preserves_unopened_path(self) -> None:
        module = load_generator_module(self.source.generator)
        parent = self.root / "private-open-failure"
        parent.mkdir()
        parent_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        real_open_directory = module.open_directory_at

        def fail_open_directory(_parent_fd: int, _name: str, _label: str) -> int:
            raise OSError(24, "synthetic descriptor exhaustion")

        module.open_directory_at = fail_open_directory
        try:
            with self.assertRaisesRegex(module.BundleError, "retained path"):
                module.create_private_directory_at(parent_fd)
        finally:
            module.open_directory_at = real_open_directory
            os.close(parent_fd)
        retained = list(parent.iterdir())
        self.assertEqual(len(retained), 1)
        self.assertTrue(retained[0].is_dir())
        self.assertTrue(retained[0].name.startswith(".easyroms-bundle."))

        competitor_parent = self.root / "private-open-competitor"
        competitor_parent.mkdir()
        parent_fd = os.open(
            competitor_parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        swapped: dict[str, pathlib.Path] = {}

        def swap_then_fail(parent_descriptor: int, name: str, _label: str) -> int:
            displaced = f"{name}.owned-displaced"
            os.rename(
                name,
                displaced,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            os.mkdir(name, 0o700, dir_fd=parent_descriptor)
            competitor_fd = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                dir_fd=parent_descriptor,
            )
            try:
                marker_fd = os.open(
                    "COMPETITOR",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=competitor_fd,
                )
                os.write(marker_fd, b"must survive failed open cleanup\n")
                os.close(marker_fd)
            finally:
                os.close(competitor_fd)
            swapped["competitor"] = competitor_parent / name
            swapped["displaced"] = competitor_parent / displaced
            raise OSError(24, "synthetic descriptor exhaustion after path swap")

        module.open_directory_at = swap_then_fail
        try:
            with self.assertRaisesRegex(module.BundleError, "retained path"):
                module.create_private_directory_at(parent_fd)
        finally:
            module.open_directory_at = real_open_directory
            os.close(parent_fd)
        self.assertEqual(
            (swapped["competitor"] / "COMPETITOR").read_bytes(),
            b"must survive failed open cleanup\n",
        )
        self.assertTrue(swapped["displaced"].is_dir())

        opened_competitor_parent = self.root / "private-open-returned-competitor"
        opened_competitor_parent.mkdir()
        parent_fd = os.open(
            opened_competitor_parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        swapped.clear()

        def swap_then_open_competitor(
            parent_descriptor: int, name: str, label: str
        ) -> int:
            displaced = f"{name}.owned-displaced"
            os.rename(
                name,
                displaced,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            os.mkdir(name, 0o700, dir_fd=parent_descriptor)
            swapped["competitor"] = opened_competitor_parent / name
            swapped["displaced"] = opened_competitor_parent / displaced
            return real_open_directory(parent_descriptor, name, label)

        module.open_directory_at = swap_then_open_competitor
        try:
            with self.assertRaisesRegex(
                module.BundleError,
                "changed or was not empty after creation; path was preserved",
            ):
                module.create_private_directory_at(parent_fd)
        finally:
            module.open_directory_at = real_open_directory
            os.close(parent_fd)
        self.assertTrue(swapped["competitor"].is_dir())
        self.assertTrue(swapped["displaced"].is_dir())

    def test_generator_uses_no_path_deletion_or_named_raw_cache(self) -> None:
        module = load_generator_module(self.source.generator)
        source = self.source.generator.read_text(encoding="utf-8")
        self.assertFalse(hasattr(module, "create_unlinked_cache_file"))
        self.assertFalse(hasattr(module, "clear_directory_fd"))
        self.assertFalse(hasattr(module, "cleanup_private_directory"))
        self.assertNotIn("os.unlink(", source)
        self.assertNotIn("os.rmdir(", source)

    def test_rejects_unsafe_source_epoch_upper_bound(self) -> None:
        result = self.source.run_generator(
            self.package, self.root / "huge-epoch-output", epoch=1 << 80
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SOURCE_DATE_EPOCH must be in", result.stderr)

    def test_profile_and_baseline_must_be_head_blobs_below_deploy(self) -> None:
        outside = self.source.mainline / "outside-profile.json"
        outside_baseline = self.source.mainline / "outside-baseline.json"
        shutil.copy2(self.source.card, outside)
        shutil.copy2(self.source.baseline, outside_baseline)
        self.source.commit("tracked outside deployment inputs")
        package = self.source.package(self.root / "outside-package")
        result = self.source.run_generator(
            package, self.root / "outside-output", card=outside
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be inside mainline/deploy", result.stderr)
        result = self.source.run_generator(
            package,
            self.root / "outside-baseline-output",
            baseline=outside_baseline,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be inside mainline/deploy", result.stderr)

        ignored = self.source.mainline / "deploy/profiles/ignored.json"
        with (self.source.mainline / ".gitignore").open("a", encoding="utf-8") as handle:
            handle.write("/deploy/profiles/ignored.json\n")
        self.source.commit("ignore test-only profile")
        shutil.copy2(self.source.card, ignored)
        package = self.source.package(self.root / "ignored-package")
        result = self.source.run_generator(
            package, self.root / "ignored-output", card=ignored
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("committed source", result.stderr)

        git(
            self.source.repo,
            "rm",
            "mainline/deploy/templates/switch-boot.sh.in",
        )
        self.source.commit("remove required committed template")
        package = self.source.package(self.root / "missing-template-package")
        result = self.source.run_generator(
            package, self.root / "missing-template-output"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("committed source", result.stderr)

    def test_end_to_end_rejects_wrong_boot_relationships(self) -> None:
        cases = [
            ({"root_spec": "/dev/mmcblk0p2"}, "root_spec"),
            ({"console": "ttyS2,1500000n8"}, "console must be exactly"),
            ({"dtb_compatible": "rockchip,rk3326"}, "DTB compatible"),
        ]
        for index, (changes, message) in enumerate(cases):
            with self.subTest(message=message):
                package = self.source.package(
                    self.root / f"wrong-relationship-{index}", **changes
                )
                result = self.source.run_generator(
                    package, self.root / f"wrong-relationship-output-{index}"
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_package_path_swap_to_fifo_is_rejected_without_blocking(self) -> None:
        module = load_generator_module(self.source.generator)
        output = self.root / "package-fifo-swap-output"
        displaced = self.package.with_name(f"{self.package.name}.owned-displaced")
        real_establish = module.establish_repository_binding

        def swap_after_package_read(
            package: dict[str, Any], card: pathlib.Path, baseline: pathlib.Path
        ) -> dict[str, Any]:
            binding = real_establish(package, card, baseline)
            self.package.rename(displaced)
            os.mkfifo(self.package)
            return binding

        module.establish_repository_binding = swap_after_package_read
        try:
            with self.assertRaisesRegex(
                module.BundleError, "package source identity changed before copying"
            ):
                module.build_bundle(
                    argparse.Namespace(
                        package_tar=str(self.package),
                        card_profile=str(self.source.card),
                        current_baseline=str(self.source.baseline),
                        purpose="synthetic-generator-fixture",
                        source_date_epoch=EPOCH,
                        output_dir=str(output),
                    )
                )
        finally:
            module.establish_repository_binding = real_establish
        self.assertTrue(self.package.exists())
        self.assertTrue(displaced.is_file())
        self.assertFalse((output / f"r46h-easyroms-{BUILD_ID}").exists())
        retained = list(output.glob(".easyroms-bundle.*"))
        self.assertEqual(len(retained), 1, retained)
        self.assertTrue((retained[0] / "payload").is_dir())

    def test_repository_binding_recheck_detects_prepublication_change(self) -> None:
        module = load_generator_module(self.source.generator)
        package = module.read_package(self.package)
        binding = module.establish_repository_binding(
            package, self.source.card, self.source.baseline
        )
        template = self.source.mainline / "deploy/templates/boot.ini.in"
        template.write_bytes(template.read_bytes() + b"# changed after binding\n")
        with self.assertRaisesRegex(module.BundleError, "must be completely clean"):
            module.recheck_repository_binding(binding)

    def test_repository_binding_recheck_rejects_late_index_masking(self) -> None:
        module = load_generator_module(self.source.generator)
        package = module.read_package(self.package)
        binding = module.establish_repository_binding(
            package, self.source.card, self.source.baseline
        )
        masked_path = "mainline/deploy/templates/boot.ini.in"
        git(self.source.repo, "update-index", "--assume-unchanged", masked_path)
        try:
            with self.assertRaisesRegex(module.BundleError, "unsafe index state"):
                module.recheck_repository_binding(binding)
        finally:
            git(
                self.source.repo,
                "update-index",
                "--no-assume-unchanged",
                masked_path,
            )

    def test_final_repository_recheck_rejects_postpublication_index_masking(self) -> None:
        module = load_generator_module(self.source.generator)
        output = self.root / "late-index-mask-output"
        masked_path = "mainline/deploy/templates/boot.ini.in"
        real_recheck = module.recheck_repository_binding
        calls = 0

        def mask_after_first_recheck(binding: dict[str, Any]) -> None:
            nonlocal calls
            real_recheck(binding)
            calls += 1
            if calls == 1:
                git(
                    self.source.repo,
                    "update-index",
                    "--assume-unchanged",
                    masked_path,
                )

        module.recheck_repository_binding = mask_after_first_recheck
        try:
            with self.assertRaisesRegex(module.BundleError, "retained"):
                module.build_bundle(
                    argparse.Namespace(
                        package_tar=str(self.package),
                        card_profile=str(self.source.card),
                        current_baseline=str(self.source.baseline),
                        purpose="synthetic-generator-fixture",
                        source_date_epoch=EPOCH,
                        output_dir=str(output),
                    )
                )
        finally:
            module.recheck_repository_binding = real_recheck
            git(
                self.source.repo,
                "update-index",
                "--no-assume-unchanged",
                masked_path,
            )
        self.assertEqual(calls, 1)
        self.assertTrue((output / f"r46h-easyroms-{BUILD_ID}").is_dir())
        self.assertTrue(
            (output / f"r46h-easyroms-{BUILD_ID}.tar.gz").is_file()
        )

    def test_cli_exposes_no_provenance_bypass(self) -> None:
        result = subprocess.run(
            ["python3", str(self.source.generator), "--help"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertNotIn("bypass", result.stdout.lower())
        self.assertNotIn("allow-dirty", result.stdout.lower())

    def test_templates_do_not_embed_release_specific_versions(self) -> None:
        for template in TEMPLATES.iterdir():
            if template.is_file():
                text = template.read_text(encoding="utf-8")
                self.assertNotIn("v0.3-eot1", text, template.name)
                self.assertNotIn("v0.4-dsi396", text, template.name)
                self.assertNotIn("v0.5-ldo7", text, template.name)
                self.assertNotIn("v0.6-ldo7", text, template.name)
                self.assertNotIn("v0.7-host-timers", text, template.name)
                self.assertNotIn("v0.8-bootloader-handoff", text, template.name)


class PackageTrustTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        CACHE.mkdir(parents=True, exist_ok=True)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix=".easyroms-package-trust-test.", dir=CACHE
        )
        self.root = pathlib.Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_recomputes_module_tree_and_requires_boot_script(self) -> None:
        package = GENERATOR_MODULE.read_package(build_small_package(self.root / "valid"))
        self.assertEqual(package["module_count"], 4)
        self.assertEqual(package["module_file_count"], 5)
        self.assertEqual(package["source_snapshot_sha256"], "b" * 64)

        archive = build_small_package(
            self.root / "missing-boot",
            mutate=lambda entries, package_name: entries.__setitem__(
                slice(None),
                [
                    item
                    for item in entries
                    if item["name"] != f"{package_name}/boot/boot.ini.test"
                ],
            ),
        )
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "required payload files"):
            GENERATOR_MODULE.read_package(archive)

    def test_rejects_release_source_and_module_tree_mismatches(self) -> None:
        cases = [
            (
                build_small_package(
                    self.root / "release",
                    release="6.12.99-r46h-mainline-another-build",
                ),
                "kernel release does not match build ID",
            ),
            (
                build_small_package(self.root / "commit", source_commit="unknown"),
                "source commit",
            ),
            (
                build_small_package(self.root / "snapshot", source_snapshot="not-a-sha256"),
                "source snapshot",
            ),
            (
                build_small_package(self.root / "tree", tree_hash="0" * 64),
                "module tree hash mismatch",
            ),
        ]
        for archive, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, message):
                    GENERATOR_MODULE.read_package(archive)

    def test_rejects_files_outside_explicit_allowlist(self) -> None:
        archive = build_small_package(
            self.root,
            extra_payloads={"rootfs/etc/unexpected": b"must not be extracted\n"},
        )
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "unsupported payload files"):
            GENERATOR_MODULE.read_package(archive)

    def test_rejects_noncanonical_tar_paths_types_and_metadata(self) -> None:
        def duplicate(entries: list[ArchiveEntry], _package_name: str) -> None:
            entries.append(copy.deepcopy(entries[-1]))

        def alias(entries: list[ArchiveEntry], package_name: str) -> None:
            target = next(item for item in entries if item["name"] == f"{package_name}/boot")
            target["name"] = f"{package_name}//boot"

        def wrong_order(entries: list[ArchiveEntry], _package_name: str) -> None:
            entries[1], entries[2] = entries[2], entries[1]

        def missing_directory(entries: list[ArchiveEntry], package_name: str) -> None:
            entries[:] = [
                item for item in entries if item["name"] != f"{package_name}/boot"
            ]

        def extra_directory(entries: list[ArchiveEntry], package_name: str) -> None:
            extra = copy.deepcopy(entries[0])
            extra["name"] = f"{package_name}/empty"
            entries.append(extra)

        cases: list[tuple[str, ArchiveMutation, str, int]] = [
            ("alias", alias, "non-canonical package path", tarfile.GNU_FORMAT),
            ("mode", mutate_member("MANIFEST", mode=0o777), "metadata", tarfile.GNU_FORMAT),
            ("directory-mode", mutate_member("boot", mode=0o777), "metadata", tarfile.GNU_FORMAT),
            ("uid", mutate_member("MANIFEST", uid=1), "metadata", tarfile.GNU_FORMAT),
            ("gid", mutate_member("MANIFEST", gid=1), "metadata", tarfile.GNU_FORMAT),
            ("uname", mutate_member("MANIFEST", uname="root"), "metadata", tarfile.GNU_FORMAT),
            ("gname", mutate_member("MANIFEST", gname="root"), "metadata", tarfile.GNU_FORMAT),
            ("aregtype", mutate_member("MANIFEST", type=tarfile.AREGTYPE), "member type", tarfile.GNU_FORMAT),
            (
                "symlink",
                mutate_member("MANIFEST", type=tarfile.SYMTYPE, linkname="target", data=b""),
                "metadata|member type",
                tarfile.GNU_FORMAT,
            ),
            ("duplicate", duplicate, "duplicate package member", tarfile.GNU_FORMAT),
            ("order", wrong_order, "canonical tree order", tarfile.GNU_FORMAT),
            ("missing-directory", missing_directory, "directory set is not canonical", tarfile.GNU_FORMAT),
            ("extra-directory", extra_directory, "directory set is not canonical", tarfile.GNU_FORMAT),
            (
                "sparse",
                mutate_member(
                    "MANIFEST",
                    type=tarfile.GNUTYPE_SPARSE,
                    data=b"",
                ),
                "hidden tar extension",
                tarfile.GNU_FORMAT,
            ),
            (
                "pax",
                mutate_member("MANIFEST", pax_headers={"comment": "not canonical"}),
                "GNU tar format|hidden tar extension",
                tarfile.PAX_FORMAT,
            ),
        ]
        for name, mutation, message, archive_format in cases:
            with self.subTest(name=name):
                archive = build_small_package(
                    self.root / name,
                    mutate=mutation,
                    tar_format=archive_format,
                )
                with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, message):
                    GENERATOR_MODULE.read_package(archive)

    def test_rejects_hidden_raw_tar_extensions_trailing_data_and_mtime(self) -> None:
        valid = build_small_package(self.root / "raw-valid")
        package_name = f"r46h-mainline-test-{BUILD_ID}"
        cases: list[tuple[str, Callable[[bytes], bytes], str]] = [
            (
                "unnecessary-longname",
                lambda raw: tar_extension_record(
                    tarfile.GNUTYPE_LONGNAME,
                    f"{package_name}/".encode() + b"\0",
                )
                + raw,
                "longname record is not canonical or necessary",
            ),
            (
                "longlink",
                lambda raw: tar_extension_record(
                    tarfile.GNUTYPE_LONGLINK, b"hidden-target\0"
                )
                + raw,
                "forbidden hidden tar extension",
            ),
            (
                "empty-global-pax",
                lambda raw: tar_extension_record(tarfile.XGLTYPE, b"") + raw,
                "forbidden hidden tar extension",
            ),
            (
                "after-eoa",
                lambda raw: raw[:-1] + b"X",
                "data after tar end marker",
            ),
            (
                "mtime",
                lambda raw: replace_tar_header_field(
                    raw, 0, slice(136, 148), f"{EPOCH + 1:011o}".encode() + b"\0"
                ),
                "mtimes are inconsistent|does not match MANIFEST",
            ),
        ]
        for name, transform, message in cases:
            with self.subTest(name=name):
                archive = rewrite_raw_archive(valid, self.root / name, transform)
                with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, message):
                    GENERATOR_MODULE.read_package(archive)

        concatenated_root = self.root / "concatenated-gzip"
        concatenated_root.mkdir()
        concatenated = concatenated_root / valid.name
        concatenated.write_bytes(valid.read_bytes() + gzip_bytes(b"hidden stream"))
        with self.assertRaisesRegex(
            GENERATOR_MODULE.BundleError, "trailing or concatenated gzip data"
        ):
            GENERATOR_MODULE.read_package(concatenated)

        wrong_os_root = self.root / "wrong-gzip-os"
        wrong_os_root.mkdir()
        wrong_os = wrong_os_root / valid.name
        wrong_os_bytes = bytearray(valid.read_bytes())
        wrong_os_bytes[9] = 255
        wrong_os.write_bytes(wrong_os_bytes)
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "gzip header"):
            GENERATOR_MODULE.read_package(wrong_os)

    def test_rejects_package_budgets_before_logical_extraction(self) -> None:
        valid = build_small_package(self.root / "budget-valid")
        limits = [
            ("MAX_COMPRESSED_PACKAGE_BYTES", 16, "compressed byte budget"),
            ("MAX_RAW_TAR_BYTES", 1024, "raw tar byte budget"),
            ("MAX_PACKAGE_MEMBERS", 1, "member-count budget"),
            ("MAX_SINGLE_MEMBER_BYTES", 1, "single-member byte budget"),
            ("MAX_TOTAL_MEMBER_BYTES", 8, "total member byte budget"),
        ]
        for attribute, limit, message in limits:
            with self.subTest(attribute=attribute):
                original = getattr(GENERATOR_MODULE, attribute)
                setattr(GENERATOR_MODULE, attribute, limit)
                try:
                    with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, message):
                        GENERATOR_MODULE.read_package(valid)
                finally:
                    setattr(GENERATOR_MODULE, attribute, original)

    def test_rejects_deep_component_paths_without_python_recursion(self) -> None:
        deep_name = "/".join(["d"] * 1100 + ["MANIFEST"])

        def deepen_manifest(
            entries: list[ArchiveEntry], package_name: str
        ) -> None:
            manifest = next(
                item
                for item in entries
                if item["name"] == f"{package_name}/MANIFEST"
            )
            manifest["name"] = f"{package_name}/{deep_name}"

        archive = build_small_package(
            self.root / "deep-components", mutate=deepen_manifest
        )
        with self.assertRaisesRegex(
            GENERATOR_MODULE.BundleError, "component budget|directory-depth budget"
        ):
            GENERATOR_MODULE.read_package(archive)

    def test_package_source_requires_stable_regular_nofollow_nonblocking_file(self) -> None:
        valid = build_small_package(self.root / "stable-source")
        symlink = self.root / "package-symlink.tar.gz"
        symlink.symlink_to(valid)
        fifo = self.root / "package-fifo.tar.gz"
        os.mkfifo(fifo)
        directory = self.root / "package-directory.tar.gz"
        directory.mkdir()
        cases = [symlink, fifo, directory]
        if pathlib.Path("/dev/null").exists():
            cases.append(pathlib.Path("/dev/null"))
        for source in cases:
            with self.subTest(source=str(source)):
                with self.assertRaisesRegex(
                    GENERATOR_MODULE.BundleError,
                    "safely open|stable regular non-symlink file",
                ):
                    GENERATOR_MODULE.read_package(source)

    def test_package_source_swap_during_parse_is_rejected_at_end_recheck(self) -> None:
        module = load_generator_module()
        package = build_small_package(self.root / "parse-source-swap")
        displaced = package.with_name(f"{package.name}.owned-displaced")
        real_decompress = module.decompress_package_to_temp
        swapped = False

        def swap_after_decompress(
            package_fd: int, compressed_size: int
        ) -> tuple[Any, int, int, str]:
            nonlocal swapped
            result = real_decompress(package_fd, compressed_size)
            package.rename(displaced)
            package.write_bytes(b"regular competitor\n")
            swapped = True
            return result

        module.decompress_package_to_temp = swap_after_decompress
        try:
            with self.assertRaisesRegex(
                module.BundleError, "source identity changed while being read"
            ):
                module.read_package(package)
        finally:
            module.decompress_package_to_temp = real_decompress
        self.assertTrue(swapped)
        self.assertEqual(package.read_bytes(), b"regular competitor\n")
        self.assertTrue(displaced.is_file())


class ProfileAndRelationshipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.card = json.loads(CARD.read_text(encoding="utf-8"))
        self.new_card = json.loads(NEW_CARD.read_text(encoding="utf-8"))
        self.baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        self.package = {
            "release": "6.12.99-r46h-mainline-v9-fixture",
            "build_id": BUILD_ID,
            "root_spec": "PARTUUID=c9f931c9-02",
            "console": "ttyS2,115200n8",
            "source_git_commit": "a" * 40,
            "manifest": {"dtb_compatible": "rockchip,rk3326-r46h-linux"},
        }

    def relationships(self, **package_changes: Any) -> None:
        package = {**self.package, **package_changes}
        GENERATOR_MODULE.validate_deployment_relationships(
            package,
            self.card,
            self.baseline,
            image_name="Image.mainline-v9-fixture.gz",
            dtb_name="rk3326-r46h-mainline-v9-fixture.dtb",
            boot_name="boot.ini.v9-fixture",
            boot_data=b"new boot state\n",
        )

    def test_json_rejects_duplicate_keys_and_nonfinite_numbers(self) -> None:
        invalid = {
            "duplicate": b'{"outer":{"value":1,"value":2}}',
            "nan": b'{"value":NaN}',
            "infinity": b'{"value":Infinity}',
            "negative-infinity": b'{"value":-Infinity}',
            "overflow-to-infinity": b'{"value":1e9999}',
        }
        for name, raw in invalid.items():
            with self.subTest(name=name):
                with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "invalid profile"):
                    GENERATOR_MODULE.load_json_bytes(raw, "profile")

    def test_accepts_exactly_the_two_audited_profile_geometry_pairs(self) -> None:
        self.assertEqual(
            set(GENERATOR_MODULE.AUDITED_CARD_GEOMETRIES),
            {
                "hl-r46h-v22-g92-v1",
                "hl-r46h-v22-g92-31719424000-v1",
            },
        )
        GENERATOR_MODULE.validate_profiles(self.card, self.baseline)
        GENERATOR_MODULE.validate_profiles(self.new_card, self.baseline)

        unknown = copy.deepcopy(self.new_card)
        unknown["profile_id"] = "hl-r46h-v22-g92-unknown-v1"
        with self.assertRaisesRegex(
            GENERATOR_MODULE.BundleError, "unsupported card profile ID"
        ):
            GENERATOR_MODULE.validate_profiles(unknown, self.baseline)

        old_id_with_new_geometry = copy.deepcopy(self.new_card)
        old_id_with_new_geometry["profile_id"] = "hl-r46h-v22-g92-v1"
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "exactly match"):
            GENERATOR_MODULE.validate_profiles(old_id_with_new_geometry, self.baseline)

        new_id_with_old_geometry = copy.deepcopy(self.card)
        new_id_with_old_geometry["profile_id"] = "hl-r46h-v22-g92-31719424000-v1"
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "exactly match"):
            GENERATOR_MODULE.validate_profiles(new_id_with_old_geometry, self.baseline)

    def test_rejects_uboot_traversal_and_partition_geometry_errors(self) -> None:
        self.card["uboot"]["console_dtb_path"] = "../outside.dtb"
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "unsafe U-Boot console DTB"):
            GENERATOR_MODULE.validate_profiles(self.card, self.baseline)

        self.setUp()
        self.card["card"]["root"]["number"] = 4
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "partition numbers"):
            GENERATOR_MODULE.validate_profiles(self.card, self.baseline)

        self.setUp()
        self.card["card"]["easyroms"]["offset"] += 512
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "not contiguous"):
            GENERATOR_MODULE.validate_profiles(self.card, self.baseline)

    def test_rejects_non_audited_uboot_and_fallback_identity(self) -> None:
        self.card["uboot"]["dtb_sha256"] = "0" * 64
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "U-Boot identity"):
            GENERATOR_MODULE.validate_profiles(self.card, self.baseline)

        self.setUp()
        self.card["fallback"]["release"] = "6.12.99-r46h-mainline-v9-not-known-good"
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "fallback identity"):
            GENERATOR_MODULE.validate_profiles(self.card, self.baseline)

    def test_rejects_unbounded_integers_and_non_audited_card_geometry(self) -> None:
        self.card["card"]["whole_size"] = 1 << 80
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "integer in"):
            GENERATOR_MODULE.validate_profiles(self.card, self.baseline)

        self.setUp()
        self.baseline["payload_anchors"][0]["size"] = 1 << 64
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "integer in"):
            GENERATOR_MODULE.validate_profiles(self.card, self.baseline)

        self.setUp()
        self.card["fallback"]["module_count"] = 1 << 80
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "integer in"):
            GENERATOR_MODULE.validate_profiles(self.card, self.baseline)

        self.setUp()
        self.card["card"]["g92_prefix_sha256"] = "0" * 64
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "exactly match"):
            GENERATOR_MODULE.validate_profiles(self.card, self.baseline)

    def test_rejects_exact_root_console_dtb_and_baseline_commit_relationships(self) -> None:
        cases = [
            ({"root_spec": "/dev/mmcblk0p2"}, "root_spec"),
            ({"console": "ttyS2,1500000n8"}, "console must be exactly"),
            ({"manifest": {"dtb_compatible": "rockchip,rk3326"}}, "DTB compatible"),
            (
                {"source_git_commit": self.baseline["source_git_commit"]},
                "must differ from the current baseline commit",
            ),
        ]
        for changes, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, message):
                    self.relationships(**changes)

        self.card["card"]["root"]["partuuid"] = "deadbeef-02"
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "audited R46H value"):
            self.relationships()

    def test_rejects_release_and_boot_path_collisions(self) -> None:
        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "releases must be distinct"):
            self.relationships(release=self.card["fallback"]["release"])

        with self.assertRaisesRegex(GENERATOR_MODULE.BundleError, "BOOT paths collide"):
            GENERATOR_MODULE.validate_deployment_relationships(
                self.package,
                self.card,
                self.baseline,
                image_name=self.baseline["boot"]["image_path"],
                dtb_name="rk3326-r46h-mainline-v9-fixture.dtb",
                boot_name="boot.ini.v9-fixture",
                boot_data=b"new boot state\n",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
