#!/usr/bin/env python3
"""Executable, block-device-free coverage for EASYROMS action policies.

The slow test is intentionally root/container-only because the target fixture
models the ownership and mode transitions performed by the real bootstrap.  It
never receives or opens a physical block-device path: both the host stager and
target bootstrap operate solely on private directories below mainline/out/.cache.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from typing import Any


MAINLINE = pathlib.Path(__file__).resolve().parents[1]
CACHE = MAINLINE / "out/.cache"
SUPPORT_PATH = pathlib.Path(__file__).with_name("test-generate-easyroms-bundle.py")
RUN_ENV = "R46H_RUN_ACTION_POLICY_INTEGRATION"


def load_support():
    spec = importlib.util.spec_from_file_location("r46h_generator_test_support", SUPPORT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load EASYROMS generator test support")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUPPORT = load_support()


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(path: pathlib.Path) -> str:
    return SUPPORT.digest(path)


def parse_kv(path: pathlib.Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or "=" not in line:
            raise AssertionError(f"malformed key/value fixture: {path}")
        key, value = line.split("=", 1)
        if key in result or not value:
            raise AssertionError(f"duplicate or empty fixture field {key}: {path}")
        result[key] = value
    return result


def filesystem_state(root: pathlib.Path) -> list[tuple[str, str, int, int, int, str]]:
    """Capture content, type, mode and ownership without following symlinks."""

    result: list[tuple[str, str, int, int, int, str]] = []
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        relative = path.relative_to(root).as_posix()
        mode = stat.S_IMODE(metadata.st_mode)
        if stat.S_ISDIR(metadata.st_mode):
            kind, identity = "directory", ""
        elif stat.S_ISREG(metadata.st_mode):
            kind, identity = "file", digest(path)
        elif stat.S_ISLNK(metadata.st_mode):
            kind, identity = "symlink", os.readlink(path)
        else:
            kind, identity = "special", str(stat.S_IFMT(metadata.st_mode))
        result.append((relative, kind, mode, metadata.st_uid, metadata.st_gid, identity))
    return result


def module_tree_sha256(release: str, files: dict[str, bytes]) -> str:
    manifest = "".join(
        f"{digest_bytes(data)}  rootfs/lib/modules/{release}/{relative}\n"
        for relative, data in sorted(files.items())
    )
    return digest_bytes(manifest.encode("utf-8"))


class ActionPolicyIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        CACHE.mkdir(parents=True, exist_ok=True)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix=".r46h-action-policy-test.", dir=CACHE
        )
        self.root = pathlib.Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def configure_hermetic_source(self) -> tuple[Any, pathlib.Path, dict[str, Any]]:
        """Create tiny, internally consistent BOOT/baseline/profile identities.

        Production identity checks are not weakened.  The copied generator in
        the private Git fixture is rebound to the tiny fixture identities and
        committed before the canonical package is built, so its provenance
        checks still exercise a clean exact-HEAD source tree.
        """

        source = SUPPORT.HermeticRepository(self.root / "source")
        profile_path = source.new_card
        baseline_path = source.baseline
        generator_path = source.generator

        current = {
            "boot.ini": b"synthetic current active boot\n",
            "boot.ini.v0.3-eot1": b"synthetic current active boot\n",
            "Image.mainline-v0.3-eot1.gz": b"synthetic current Image\n",
            "rk3326-r46h-mainline-v0.3-eot1.dtb": b"synthetic current DTB\n",
        }
        anchor_name = "CURRENT-ANCHOR"
        anchor_data = b"synthetic current payload anchor\n"
        fallback_release = "6.12.99-r46h-mainline-v0.2"
        fallback_modules = {
            "fallback.ko": b"synthetic fallback module\n",
            "modules.dep": b"fallback.ko:\n",
        }
        fallback = {
            "release": fallback_release,
            "boot_path": "boot.ini.v0.2-known-good",
            "boot_test_path": "boot.ini.test",
            "boot_size": len(b"synthetic fallback boot\n"),
            "boot_sha256": digest_bytes(b"synthetic fallback boot\n"),
            "image_path": "Image.mainline-test.gz",
            "image_size": len(b"synthetic fallback Image\n"),
            "image_sha256": digest_bytes(b"synthetic fallback Image\n"),
            "dtb_path": "rk3326-r46h-mainline-test.dtb",
            "dtb_size": len(b"synthetic fallback DTB\n"),
            "dtb_sha256": digest_bytes(b"synthetic fallback DTB\n"),
            "module_count": 1,
            "module_file_count": len(fallback_modules),
            "module_tree_sha256_allowed": [
                module_tree_sha256(fallback_release, fallback_modules)
            ],
        }
        uboot_data = b"synthetic U-Boot DTB\n"
        uboot = {
            "root_dtb_path": "arkos4clone-uboot.dtb",
            "console_dtb_path": "consoles/r46h/arkos4clone-uboot.dtb",
            "dtb_size": len(uboot_data),
            "dtb_sha256": digest_bytes(uboot_data),
        }
        prefix_data = b"\0" * (16 * 1024 * 1024)

        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        old_prefix_sha = profile["card"]["g92_prefix_sha256"]
        profile["card"]["g92_prefix_sha256"] = digest_bytes(prefix_data)
        profile["uboot"] = uboot
        profile["fallback"] = fallback
        profile_path.write_text(
            json.dumps(profile, indent=2, sort_keys=False) + "\n", encoding="utf-8"
        )

        baseline = {
            "format_version": 1,
            "baseline_id": "v0.3-eot1",
            "release": "6.12.99-r46h-mainline-v0.3-eot1",
            "payload_name": "r46h-v0.3-eot1",
            "source_git_commit": "c" * 40,
            "boot": {
                "active_path": "boot.ini",
                "candidate_path": "boot.ini.v0.3-eot1",
                "candidate_size": len(current["boot.ini.v0.3-eot1"]),
                "candidate_sha256": digest_bytes(current["boot.ini.v0.3-eot1"]),
                "image_path": "Image.mainline-v0.3-eot1.gz",
                "image_size": len(current["Image.mainline-v0.3-eot1.gz"]),
                "image_sha256": digest_bytes(current["Image.mainline-v0.3-eot1.gz"]),
                "dtb_path": "rk3326-r46h-mainline-v0.3-eot1.dtb",
                "dtb_size": len(current["rk3326-r46h-mainline-v0.3-eot1.dtb"]),
                "dtb_sha256": digest_bytes(
                    current["rk3326-r46h-mainline-v0.3-eot1.dtb"]
                ),
            },
            "payload_anchors": [
                {
                    "path": anchor_name,
                    "size": len(anchor_data),
                    "sha256": digest_bytes(anchor_data),
                }
            ],
        }
        baseline_path.write_text(
            json.dumps(baseline, indent=2, sort_keys=False) + "\n", encoding="utf-8"
        )

        generator = generator_path.read_text(encoding="utf-8")
        generator, prefix_replacements = re.subn(
            re.escape(old_prefix_sha), profile["card"]["g92_prefix_sha256"], generator
        )
        self.assertEqual(prefix_replacements, 1)
        identity_pattern = re.compile(
            r"AUDITED_UBOOT_IDENTITY = \{.*?\n\}\n"
            r"AUDITED_FALLBACK_IDENTITY = \{.*?\n\}\n\n\nclass BundleError",
            re.DOTALL,
        )
        replacement = (
            "AUDITED_UBOOT_IDENTITY = "
            + json.dumps(uboot, indent=4, sort_keys=False)
            + "\nAUDITED_FALLBACK_IDENTITY = "
            + json.dumps(fallback, indent=4, sort_keys=False)
            + "\n\n\nclass BundleError"
        )
        generator, identity_replacements = identity_pattern.subn(replacement, generator)
        self.assertEqual(identity_replacements, 1)
        generator_path.write_text(generator, encoding="utf-8")
        generator_path.chmod(0o755)
        source.commit("bind executable policy fixture identities")

        package = source.package(self.root / "canonical-input")
        fixture = {
            "profile": profile,
            "baseline": baseline,
            "current": current,
            "anchor_name": anchor_name,
            "anchor_data": anchor_data,
            "fallback_boot": b"synthetic fallback boot\n",
            "fallback_image": b"synthetic fallback Image\n",
            "fallback_dtb": b"synthetic fallback DTB\n",
            "fallback_modules": fallback_modules,
            "uboot_data": uboot_data,
            "prefix_data": prefix_data,
        }
        return source, package, fixture

    def generate_bundle(
        self,
        source: Any,
        package: pathlib.Path,
        output: pathlib.Path,
        action_policy: str | None,
    ) -> pathlib.Path:
        args = [
            sys.executable,
            str(source.generator),
            "--package-tar",
            str(package),
            "--card-profile",
            str(source.new_card),
            "--current-baseline",
            str(source.baseline),
            "--purpose",
            "synthetic-action-policy-fixture",
            "--source-date-epoch",
            str(SUPPORT.EPOCH),
            "--output-dir",
            str(output),
        ]
        if action_policy is not None:
            args.extend(["--action-policy", action_policy])
        output.mkdir(parents=True)
        generated = subprocess.run(
            args,
            cwd=source.repo,
            check=False,
            text=True,
            capture_output=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(generated.returncode, 0, generated.stderr)
        return output / f"r46h-easyroms-{SUPPORT.BUILD_ID}"

    def stage_bundle(
        self,
        bundle: pathlib.Path,
        source: Any,
        fixture: dict[str, Any],
        label: str,
        *,
        include_fallback: bool = True,
        expect_success: bool = True,
    ) -> tuple[
        pathlib.Path,
        pathlib.Path | None,
        list[tuple[str, str, int, int, int, str]],
    ]:
        stage_root = pathlib.Path(
            tempfile.mkdtemp(prefix=f".r46h-stage-test.{label}.", dir=CACHE)
        )
        self.addCleanup(shutil.rmtree, stage_root)
        stage_root.chmod(0o700)
        boot = stage_root / "card/boot"
        roms = stage_root / "card/easyroms"
        current_payload = roms / fixture["baseline"]["payload_name"]
        (boot / "consoles/r46h").mkdir(parents=True)
        current_payload.mkdir(parents=True)
        (stage_root / "raw").mkdir()
        (stage_root / "receipts").mkdir(mode=0o700)
        (stage_root / "mount-state").write_text("initial\n", encoding="utf-8")
        (stage_root / "card-profile.sha256").write_text(
            digest(source.new_card) + "\n", encoding="utf-8"
        )

        for name, data in fixture["current"].items():
            (boot / name).write_bytes(data)
        fallback = fixture["profile"]["fallback"]
        if include_fallback:
            (boot / fallback["boot_path"]).write_bytes(fixture["fallback_boot"])
            (boot / fallback["boot_test_path"]).write_bytes(fixture["fallback_boot"])
            (boot / fallback["image_path"]).write_bytes(fixture["fallback_image"])
            (boot / fallback["dtb_path"]).write_bytes(fixture["fallback_dtb"])
        uboot = fixture["profile"]["uboot"]
        (boot / uboot["root_dtb_path"]).write_bytes(fixture["uboot_data"])
        (boot / uboot["console_dtb_path"]).write_bytes(fixture["uboot_data"])
        (current_payload / fixture["anchor_name"]).write_bytes(fixture["anchor_data"])
        (stage_root / "raw/prefix.bin").write_bytes(fixture["prefix_data"])
        (stage_root / "raw/fdisk.txt").write_text(
            "synthetic immutable partition table\n", encoding="utf-8"
        )
        (stage_root / "raw/p1.bin").write_bytes(b"synthetic immutable BOOT raw\n")
        boot_before = filesystem_state(boot)

        staged = subprocess.run(
            [
                "bash",
                str(bundle / "stage-on-macos.sh"),
                "--device",
                "/dev/disk4",
                "--confirm-device",
                "/dev/disk4",
                "--receipt-parent",
                str(stage_root / "receipts"),
            ],
            check=False,
            text=True,
            capture_output=True,
            env={**os.environ, "R46H_DEPLOY_STAGE_TEST_ROOT": str(stage_root)},
        )
        if not expect_success:
            self.assertNotEqual(staged.returncode, 0)
            self.assertIn("missing or unsafe fallback boot.ini", staged.stderr)
            self.assertEqual(
                (stage_root / "mount-state").read_text(encoding="utf-8").strip(),
                "initial",
            )
            self.assertEqual(filesystem_state(boot), boot_before)
            self.assertFalse(
                (roms / f"r46h-{SUPPORT.BUILD_ID}").exists(),
                "a failed preflight must not create the new payload",
            )
            return stage_root, None, boot_before
        self.assertEqual(staged.returncode, 0, staged.stderr)
        self.assertEqual(
            (stage_root / "mount-state").read_text(encoding="utf-8").strip(), "ejected"
        )
        self.assertEqual(filesystem_state(boot), boot_before)
        receipts = [path for path in (stage_root / "receipts").iterdir() if path.is_dir()]
        self.assertEqual(len(receipts), 1)
        receipt_dir = receipts[0]
        self.assertTrue((receipt_dir / "COMPLETE").is_file())
        self.assertTrue((receipt_dir / "EJECTED").is_file())
        return stage_root, receipt_dir, boot_before

    def prepare_target(
        self,
        stage_root: pathlib.Path,
        receipt_dir: pathlib.Path,
        fixture: dict[str, Any],
        label: str,
    ) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, str]:
        target_root = pathlib.Path(
            tempfile.mkdtemp(prefix=f".r46h-target-test.{label}.", dir=CACHE)
        )
        self.addCleanup(shutil.rmtree, target_root)
        target_root.chmod(0o700)
        shutil.copytree(stage_root / "card/boot", target_root / "boot")
        shutil.copytree(stage_root / "card/easyroms", target_root / "roms")
        (target_root / "lib/modules").mkdir(parents=True)
        (target_root / "run/lock").mkdir(parents=True)
        (target_root / "test-state").mkdir(parents=True)

        fallback_release = fixture["profile"]["fallback"]["release"]
        fallback_root = target_root / "lib/modules" / fallback_release
        fallback_root.mkdir()
        for relative, data in fixture["fallback_modules"].items():
            (fallback_root / relative).write_bytes(data)

        state = target_root / "test-state"
        (state / "card-profile.sha256").write_bytes(
            (stage_root / "card-profile.sha256").read_bytes()
        )
        (state / "running-release").write_text(
            fixture["baseline"]["release"] + "\n", encoding="utf-8"
        )
        (state / "roms-mount-options").write_text(
            "rw,noatime,uid=1002,gid=1002,fmask=0000,dmask=0000\n",
            encoding="utf-8",
        )
        (state / "tools-mount-state").write_text("rw\n", encoding="utf-8")
        (state / "rootfs-errors-count").write_text("0\n", encoding="utf-8")
        (state / "rootfs-kernel-log").write_text("", encoding="utf-8")

        for path in (target_root / "roms").rglob("*"):
            os.chown(path, 1002, 1002, follow_symlinks=False)
            path.chmod(0o777)
        os.chown(target_root / "roms", 1002, 1002)
        (target_root / "roms").chmod(0o777)

        trust_source = receipt_dir / "TARGET-TRUST-RECEIPT"
        trust_sha = digest(trust_source)
        receipt_hash_line = (receipt_dir / "TARGET-TRUST-RECEIPT.sha256").read_text(
            encoding="utf-8"
        )
        self.assertEqual(receipt_hash_line.split()[0], trust_sha)
        trust_fields = parse_kv(trust_source)
        payload = target_root / "roms" / trust_fields["payload"]
        trusted = target_root / "run/r46h-deploy"
        trusted.mkdir(mode=0o700)
        bootstrap = trusted / "bootstrap-target.sh"
        shutil.copyfile(payload / "bootstrap-target.sh", bootstrap)
        bootstrap.chmod(0o700)
        trust = trusted / "TARGET-TRUST-RECEIPT"
        shutil.copyfile(trust_source, trust)
        trust.chmod(0o600)
        return target_root, bootstrap, trust, trust_sha

    def run_bootstrap(
        self,
        target_root: pathlib.Path,
        bootstrap: pathlib.Path,
        trust: pathlib.Path,
        trust_sha: str,
        action: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                str(bootstrap),
                "--external-receipt",
                str(trust),
                "--external-receipt-sha256",
                trust_sha,
                "--action",
                action,
            ],
            check=False,
            text=True,
            capture_output=True,
            env={**os.environ, "R46H_DEPLOY_TARGET_TEST_ROOT": str(target_root)},
        )

    @unittest.skipUnless(
        os.environ.get(RUN_ENV) == "1",
        f"set {RUN_ENV}=1 inside the builder container",
    )
    def test_generated_modules_only_and_default_full_execute_end_to_end(self) -> None:
        if os.geteuid() != 0 or not pathlib.Path("/.dockerenv").is_file():
            self.skipTest("action-policy integration is root/container-only")

        source, package, fixture = self.configure_hermetic_source()

        modules_bundle = self.generate_bundle(
            source,
            package,
            self.root / "modules-output",
            "install-modules-only",
        )
        modules_stage, modules_receipt, modules_boot_before = self.stage_bundle(
            modules_bundle,
            source,
            fixture,
            "modules-no-fallback",
            include_fallback=False,
        )
        self.assertIsNotNone(modules_receipt)
        assert modules_receipt is not None
        modules_trust_fields = parse_kv(modules_receipt / "TARGET-TRUST-RECEIPT")
        self.assertEqual(modules_trust_fields["allowed_actions"], "install-modules")
        modules_payload = (
            modules_stage / "card/easyroms" / modules_trust_fields["payload"]
        )
        self.assertFalse((modules_payload / "switch-boot.sh").exists())
        modules_target, modules_bootstrap, modules_trust, modules_trust_sha = (
            self.prepare_target(modules_stage, modules_receipt, fixture, "modules")
        )
        modules_target_payload = modules_target / "roms" / modules_trust_fields["payload"]

        target_before_rejected_switch = filesystem_state(modules_target)
        rejected = self.run_bootstrap(
            modules_target,
            modules_bootstrap,
            modules_trust,
            modules_trust_sha,
            "switch-boot",
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn(
            "requested action is not authorized by the external receipt", rejected.stderr
        )
        self.assertEqual(filesystem_state(modules_target), target_before_rejected_switch)

        installed = self.run_bootstrap(
            modules_target,
            modules_bootstrap,
            modules_trust,
            modules_trust_sha,
            "install-modules",
        )
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertEqual(filesystem_state(modules_target / "boot"), modules_boot_before)
        modules_manifest = parse_kv(modules_target_payload / "DEPLOY-MANIFEST")
        installed_tree = modules_target / "lib/modules" / modules_manifest["kernel_release"]
        self.assertTrue(installed_tree.is_dir())
        module_receipt = modules_target_payload / "MODULES-INSTALLED"
        self.assertTrue(module_receipt.is_file())
        module_fields = parse_kv(module_receipt)
        self.assertEqual(module_fields["status"], "complete")
        self.assertEqual(
            module_fields["installed_release"], modules_manifest["kernel_release"]
        )
        self.assertEqual(
            module_fields["module_tree_sha256"], modules_manifest["module_tree_sha256"]
        )
        receipt_before_verify = module_receipt.read_bytes()
        verified_again = self.run_bootstrap(
            modules_target,
            modules_bootstrap,
            modules_trust,
            modules_trust_sha,
            "install-modules",
        )
        self.assertEqual(verified_again.returncode, 0, verified_again.stderr)
        self.assertEqual(module_receipt.read_bytes(), receipt_before_verify)
        self.assertEqual(filesystem_state(modules_target / "boot"), modules_boot_before)

        # Omit --action-policy here: this is an executable compatibility proof
        # for the historical CLI default, not merely an explicit "full" test.
        full_bundle = self.generate_bundle(
            source, package, self.root / "full-output", None
        )
        _failed_stage, failed_receipt, _failed_boot = self.stage_bundle(
            full_bundle,
            source,
            fixture,
            "full-missing-fallback",
            include_fallback=False,
            expect_success=False,
        )
        self.assertIsNone(failed_receipt)
        full_stage, full_receipt, _full_boot_before = self.stage_bundle(
            full_bundle, source, fixture, "full"
        )
        self.assertIsNotNone(full_receipt)
        assert full_receipt is not None
        full_trust_fields = parse_kv(full_receipt / "TARGET-TRUST-RECEIPT")
        self.assertEqual(
            full_trust_fields["allowed_actions"], "install-modules,switch-boot"
        )
        full_payload = full_stage / "card/easyroms" / full_trust_fields["payload"]
        self.assertTrue((full_payload / "switch-boot.sh").is_file())
        full_target, full_bootstrap, full_trust, full_trust_sha = self.prepare_target(
            full_stage, full_receipt, fixture, "full"
        )
        full_target_payload = full_target / "roms" / full_trust_fields["payload"]
        full_install = self.run_bootstrap(
            full_target, full_bootstrap, full_trust, full_trust_sha, "install-modules"
        )
        self.assertEqual(full_install.returncode, 0, full_install.stderr)
        full_switch = self.run_bootstrap(
            full_target, full_bootstrap, full_trust, full_trust_sha, "switch-boot"
        )
        self.assertEqual(full_switch.returncode, 0, full_switch.stderr)
        full_manifest = parse_kv(full_target_payload / "DEPLOY-MANIFEST")
        self.assertEqual(
            digest(full_target / "boot/boot.ini"),
            full_manifest["boot_candidate_sha256"],
        )
        switch_receipt = full_target_payload / "BOOT-SWITCHED"
        self.assertTrue(switch_receipt.is_file())
        switch_fields = parse_kv(switch_receipt)
        self.assertEqual(switch_fields["status"], "complete")
        self.assertEqual(switch_fields["active_release"], full_manifest["kernel_release"])


if __name__ == "__main__":
    unittest.main()
