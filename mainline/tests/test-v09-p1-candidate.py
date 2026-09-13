#!/usr/bin/env python3
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "mainline/out/.cache"


def load_script(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_script("r46h_v09_p1_builder", "mainline/scripts/build-v09-p1-candidate.py")
planner = load_script("r46h_v09_p1_planner", "mainline/scripts/generate-v09-p1-write-plan.py")


class V09P1CandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        CACHE.mkdir(parents=True, exist_ok=True)

    def test_boot_candidate_is_dynamic_and_reuses_v08_dtb(self) -> None:
        template = ROOT / "mainline/deploy/templates/boot.ini.in"
        rendered = builder.render_v09_boot(
            template.read_bytes(),
            compressed_image_size=14_921_320,
            uncompressed_image_size=41_570_816,
            dtb_size=49_481,
        )
        text = rendered.decode("ascii")
        self.assertIn("Image.mainline-v0.9-adc-joystick-fix.gz", text)
        self.assertIn("rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb", text)
        self.assertIn("boot.ini.v0.8-bootloader-handoff", text)
        self.assertNotIn("boot.ini.v0.2-known-good", text)
        self.assertNotIn("saveenv", text)
        changed = builder.render_v09_boot(
            template.read_bytes(),
            compressed_image_size=14_921_321,
            uncompressed_image_size=41_570_816,
            dtb_size=49_481,
        )
        self.assertNotEqual(rendered, changed)

    def test_exact_diff_allows_only_four_removals_and_two_additions(self) -> None:
        added_files = {
            builder.V09_IMAGE_NAME: (3, hashlib.sha256(b"img").hexdigest()),
            builder.V09_BOOT_NAME: (4, hashlib.sha256(b"boot").hexdigest()),
        }
        before = {
            **{path: {"size": size, "sha256": digest} for path, (size, digest) in builder.REMOVED_FILES.items()},
            **{path: {"size": size, "sha256": digest} for path, (size, digest) in builder.PRESERVED_V08_ANCHORS.items()},
            "unrelated.bin": {"size": 3, "sha256": hashlib.sha256(b"abc").hexdigest()},
        }
        after = {
            path: value for path, value in before.items() if path not in builder.REMOVED_FILES
        }
        after.update(
            {path: {"size": size, "sha256": digest} for path, (size, digest) in added_files.items()}
        )
        diff = builder.validate_exact_diff(
            before, after, ["consoles"], ["consoles"], added_files
        )
        self.assertEqual(diff["changed"], [])
        changed = dict(after)
        changed["unrelated.bin"] = {"size": 3, "sha256": hashlib.sha256(b"xyz").hexdigest()}
        with self.assertRaisesRegex(builder.BuildError, "changed unexpectedly"):
            builder.validate_exact_diff(
                before, changed, ["consoles"], ["consoles"], added_files
            )

    def test_appledouble_paths_are_rejected(self) -> None:
        for value in ("._boot.ini", "consoles/._file", "__MACOSX/file"):
            with self.subTest(value=value):
                with self.assertRaises(builder.BuildError):
                    builder.validate_fat_path(value)

    def make_modules_only_bundle(
        self, root: Path, *, action_policy: str = "install-modules-only"
    ) -> tuple[Path, object, bytes]:
        bundle = root / builder.BUNDLE_NAME
        payload = bundle / "payload"
        payload.mkdir(parents=True)
        (bundle / "stage-on-macos.sh").write_text("#!/bin/bash\n", encoding="utf-8")

        image = b"canonical-v0.9-image"
        dtb = b"canonical-v0.8-equal-dtb"
        compressed = builder.deterministic_gzip(image)
        package_tar = b"canonical-package-tar"
        profile_blob = b"{}\n"
        baseline_blob = b"{}\n"
        source_commit = "1" * 40
        source_snapshot = "2" * 64
        dtb_name = f"rk3326-r46h-mainline-{builder.BUILD_ID}.dtb"
        files = {
            ".r46h-stage-owner": b"owner\n",
            "STAGE-COMPLETE": b"complete\n",
            builder.V09_IMAGE_NAME: compressed,
            builder.V09_BOOT_NAME: b"generated-bundle-boot-is-not-used\n",
            dtb_name: dtb,
            builder.PACKAGE_TAR_NAME: package_tar,
            "bootstrap-target.sh": b"#!/bin/bash\n",
            "install-modules.sh": b"#!/bin/bash\n",
            "target-common.sh": b"#!/bin/bash\n",
        }
        manifest_fields = {
            "format_version": "3",
            "target": "HL-R46H-V22",
            "source_git_commit": source_commit,
            "source_snapshot_sha256": source_snapshot,
            "build_id": builder.BUILD_ID,
            "kernel_release": builder.RELEASE,
            "action_policy": action_policy,
            "allowed_actions": "install-modules",
            "package_name": builder.PACKAGE_NAME,
            "payload_name": f"r46h-{builder.BUILD_ID}",
            "canonical_tar": builder.PACKAGE_TAR_NAME,
            "canonical_tar_size": str(len(package_tar)),
            "canonical_tar_sha256": hashlib.sha256(package_tar).hexdigest(),
            "image_uncompressed_size": str(len(image)),
            "image_uncompressed_sha256": hashlib.sha256(image).hexdigest(),
            "boot_image": builder.V09_IMAGE_NAME,
            "boot_image_size": str(len(compressed)),
            "boot_image_sha256": hashlib.sha256(compressed).hexdigest(),
            "boot_dtb": dtb_name,
            "boot_dtb_size": str(len(dtb)),
            "boot_dtb_sha256": hashlib.sha256(dtb).hexdigest(),
            "boot_candidate": builder.V09_BOOT_NAME,
            "target_boot_switch": "disabled",
            "card_profile_id": builder.PROFILE_ID,
            "card_profile_sha256": hashlib.sha256(profile_blob).hexdigest(),
            "current_baseline_id": "v0.8-bootloader-handoff",
            "current_baseline_sha256": hashlib.sha256(baseline_blob).hexdigest(),
            "current_release": "6.12.99-r46h-mainline-v0.8-bootloader-handoff",
            "current_active_path": "boot.ini",
            "current_candidate_path": "boot.ini.v0.8-bootloader-handoff",
            "current_image_path": "Image.mainline-v0.8-bootloader-handoff.gz",
            "current_dtb_path": builder.V08_DTB_NAME,
        }
        manifest = "".join(f"{key}={value}\n" for key, value in manifest_fields.items()).encode()
        files["DEPLOY-MANIFEST"] = manifest
        for name, data in files.items():
            (payload / name).write_bytes(data)
        (bundle / "STAGE-SOURCES.sha256").write_text(
            "".join(
                f"{hashlib.sha256(data).hexdigest()}  payload/{name}\n"
                for name, data in sorted(files.items())
            ),
            encoding="utf-8",
        )

        class FakeBundleError(RuntimeError):
            pass

        class FakeDeploy:
            BundleError = FakeBundleError

            @staticmethod
            def read_package(path: Path):
                if path != payload / builder.PACKAGE_TAR_NAME:
                    raise FakeBundleError("wrong package path")
                return {
                    "build_id": builder.BUILD_ID,
                    "release": builder.RELEASE,
                    "package_name": builder.PACKAGE_NAME,
                    "root_spec": "PARTUUID=c9f931c9-02",
                    "console": "ttyS2,115200n8",
                    "source_git_commit": source_commit,
                    "source_snapshot_sha256": source_snapshot,
                    "tar_size": len(package_tar),
                    "tar_sha256": hashlib.sha256(package_tar).hexdigest(),
                    "image": image,
                    "dtb": dtb,
                }

            @staticmethod
            def establish_repository_binding(package, card_path, baseline_path):
                return {
                    "head": source_commit,
                    "snapshot_sha256": source_snapshot,
                    "blobs": {
                        builder.PROFILE_RELPATH: profile_blob,
                        builder.BASELINE_RELPATH: baseline_blob,
                        builder.BOOT_TEMPLATE_RELPATH: (
                            ROOT / builder.BOOT_TEMPLATE_RELPATH
                        ).read_bytes(),
                    },
                }

            @staticmethod
            def load_json_bytes(raw: bytes, label: str):
                return {}, hashlib.sha256(raw).hexdigest()

            @staticmethod
            def validate_profiles(card, baseline):
                return None

            @staticmethod
            def recheck_repository_binding(binding):
                return None

        return bundle, FakeDeploy(), dtb

    def test_modules_only_bundle_supplies_dynamic_canonical_sources(self) -> None:
        with tempfile.TemporaryDirectory(prefix="r46h-v09-bundle-fixture.", dir=CACHE) as temporary:
            bundle, deploy, dtb = self.make_modules_only_bundle(Path(temporary))
            with (
                mock.patch.object(builder, "import_deploy_generator", return_value=deploy),
                mock.patch.object(
                    builder,
                    "require_running_builder_matches_head",
                    return_value="3" * 64,
                ),
                mock.patch.object(builder, "V08_DTB_SIZE", len(dtb)),
                mock.patch.object(
                    builder,
                    "V08_DTB_SHA256",
                    hashlib.sha256(dtb).hexdigest(),
                ),
            ):
                sources = builder.require_modules_only_bundle(ROOT, bundle)
            self.assertEqual(sources["source_git_commit"], "1" * 40)
            self.assertEqual(
                sources["compressed_image"],
                builder.deterministic_gzip(b"canonical-v0.9-image"),
            )
            self.assertEqual(sources["builder_head_blob_sha256"], "3" * 64)

    def test_non_modules_only_bundle_is_rejected_before_source_use(self) -> None:
        with tempfile.TemporaryDirectory(prefix="r46h-v09-bundle-policy.", dir=CACHE) as temporary:
            bundle, _deploy, _dtb = self.make_modules_only_bundle(
                Path(temporary), action_policy="full"
            )
            with self.assertRaisesRegex(builder.BuildError, "action_policy"):
                builder.require_modules_only_bundle(ROOT, bundle)

    def test_atomic_publication_never_replaces_or_deletes_a_racing_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="r46h-v09-publish-race.", dir=CACHE) as temporary:
            root = Path(temporary)
            private_parent = root / "private"
            output_parent = root / "output"
            private_parent.mkdir()
            output_parent.mkdir()
            stage = private_parent / "publication"
            stage.mkdir()
            (stage / "owned.txt").write_text("owned-stage\n", encoding="utf-8")
            destination = output_parent / "candidate"
            self.assertFalse(destination.exists())
            # This mkdir is the competing publisher after the caller's early check.
            destination.mkdir()
            competitor = destination / "competitor.txt"
            competitor.write_text("must-survive\n", encoding="utf-8")
            metadata = output_parent.stat()
            deploy = builder.import_deploy_generator(ROOT)
            with self.assertRaisesRegex(builder.BuildError, "no-replace"):
                builder.publish_candidate_noreplace(
                    stage,
                    output_parent,
                    "candidate",
                    deploy,
                    (metadata.st_dev, metadata.st_ino),
                )
            self.assertEqual(competitor.read_text(encoding="utf-8"), "must-survive\n")
            self.assertEqual(
                (stage / "owned.txt").read_text(encoding="utf-8"), "owned-stage\n"
            )

    def test_atomic_publication_moves_the_proved_private_inode(self) -> None:
        with tempfile.TemporaryDirectory(prefix="r46h-v09-publish-pass.", dir=CACHE) as temporary:
            root = Path(temporary)
            private_parent = root / "private"
            output_parent = root / "output"
            private_parent.mkdir()
            output_parent.mkdir()
            stage = private_parent / "publication"
            stage.mkdir()
            marker = stage / "owned.txt"
            marker.write_text("owned-stage\n", encoding="utf-8")
            stage_identity = (stage.stat().st_dev, stage.stat().st_ino)
            parent_metadata = output_parent.stat()
            deploy = builder.import_deploy_generator(ROOT)
            published = builder.publish_candidate_noreplace(
                stage,
                output_parent,
                "candidate",
                deploy,
                (parent_metadata.st_dev, parent_metadata.st_ino),
            )
            self.assertFalse(stage.exists())
            self.assertEqual((published.stat().st_dev, published.stat().st_ino), stage_identity)
            self.assertEqual(
                (published / "owned.txt").read_text(encoding="utf-8"), "owned-stage\n"
            )

    def test_late_source_drift_blocks_publication(self) -> None:
        initial = {key: f"stable-{key}" for key in builder.LATE_REVALIDATION_KEYS}
        drifted = dict(initial)
        drifted["compressed_image"] = b"changed-after-long-build"
        drifted["deploy_helper"] = object()
        with mock.patch.object(
            builder, "require_modules_only_bundle", return_value=drifted
        ):
            with self.assertRaisesRegex(builder.BuildError, "drifted.*compressed_image"):
                builder.revalidate_canonical_sources(
                    ROOT,
                    ROOT / "mainline/out/fake-bundle",
                    initial,
                )

    def test_plan_is_one_full_boot_partition_operation(self) -> None:
        image = ROOT / "mainline/out/example-p1.img"
        payload = json.loads(
            planner.build_write_plan(
                "/dev/disk12",
                image,
                "a" * 64,
                "b" * 64,
            )
        )
        self.assertEqual(payload["profile_id"], "hl-r46h-v22-g92-31719424000-v1")
        self.assertEqual(payload["device"], "/dev/disk12")
        self.assertEqual(len(payload["operations"]), 1)
        operation = payload["operations"][0]
        self.assertEqual(operation["partition"], "boot")
        self.assertEqual(operation["source_size"], 117_440_512)
        self.assertEqual(operation["target_sha256_before"], "b" * 64)
        with self.assertRaises(planner.PlanError):
            planner.build_write_plan("/dev/disk6", image, "a" * 64, "b" * 64)
        with self.assertRaises(planner.PlanError):
            planner.build_write_plan("/dev/rdisk12", image, "a" * 64, "b" * 64)
        with self.assertRaises(planner.PlanError):
            planner.build_write_plan(
                "/dev/disk12", image, "a" * 64, "not-a-sha256"
            )

    def test_candidate_receipt_generates_a_pinned_plan_without_device_io(self) -> None:
        with tempfile.TemporaryDirectory(prefix="r46h-v09-plan-fixture.", dir=CACHE) as temporary:
            root = Path(temporary)
            candidate = root / "candidate"
            candidate.mkdir()
            image = candidate / planner.IMAGE_NAME
            with image.open("wb") as handle:
                handle.truncate(planner.P1_SIZE)
            image_sha = planner.sha256_file(image)
            status = {
                "format_version": 1,
                "state": "BUILD_COMPLETE",
                "artifact_id": planner.ARTIFACT_ID,
                "profile_id": planner.PROFILE_ID,
                "build_id": planner.BUILD_ID,
                "kernel_release": planner.RELEASE,
                "image_name": planner.IMAGE_NAME,
                "image_size": planner.P1_SIZE,
                "image_sha256": image_sha,
                "base_image_sha256": "b" * 64,
                "active_boot_ini_unchanged": True,
                "v08_dtb_reused": True,
                "added_files": [
                    "Image.mainline-v0.9-adc-joystick-fix.gz",
                    "boot.ini.v0.9-adc-joystick-fix",
                ],
                "removed_files": [
                    "Image.mainline-test.gz",
                    "boot.ini.test",
                    "boot.ini.v0.2-known-good",
                    "rk3326-r46h-mainline-test.dtb",
                ],
                "changed_preexisting_files": [],
                "free_bytes": 700_000,
                "fsck_fat_read_only_passed": True,
                "block_devices_opened": 0,
            }
            (candidate / "BUILD-STATUS.json").write_text(
                json.dumps(status, sort_keys=True) + "\n", encoding="utf-8"
            )
            (candidate / "SHA256SUMS").write_text(
                f"{image_sha}  {planner.IMAGE_NAME}\n", encoding="utf-8"
            )
            plan_parent = root / "plans"
            plan = planner.create_plan(
                ROOT,
                candidate,
                "/dev/disk12",
                "/dev/disk12",
                plan_parent,
            )
            decoded = json.loads((plan / "write-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(decoded["operations"][0]["source_sha256"], image_sha)
            self.assertEqual(
                decoded["operations"][0]["target_sha256_before"], "b" * 64
            )
            self.assertIn("physical_device_reads=0", (plan / "PLAN-INFO").read_text())
            with self.assertRaisesRegex(planner.PlanError, "confirmation"):
                planner.create_plan(
                    ROOT,
                    candidate,
                    "/dev/disk12",
                    "/dev/disk13",
                    plan_parent,
                )

    def test_builder_rejects_block_device_input_before_resolution(self) -> None:
        with self.assertRaisesRegex(builder.BuildError, "block-device"):
            builder.validate_input_clone(Path("/dev/disk12"), ROOT / "mainline/out")

    def test_builder_has_no_physical_media_command_path(self) -> None:
        source = (ROOT / "mainline/scripts/build-v09-p1-candidate.py").read_text(
            encoding="utf-8"
        )
        for forbidden in ("diskutil", "hdiutil", "rdisk", "fsck_msdos -y"):
            self.assertNotIn(forbidden, source)
        self.assertIn('"--network",\n        "none"', source)

    def test_builder_has_no_self_invalidating_v09_artifact_constants(self) -> None:
        source = (ROOT / "mainline/scripts/build-v09-p1-candidate.py").read_text(
            encoding="utf-8"
        )
        for forbidden_name in (
            "CANONICAL_MANIFEST_SHA256",
            "CANONICAL_IMAGE_SHA256",
            "V09_GZIP_SHA256",
            "V09_BOOT_SHA256",
        ):
            self.assertNotIn(forbidden_name, source)
        self.assertIn("require_modules_only_bundle", source)
        self.assertIn("source_snapshot_sha256", source)
        self.assertIn("require_running_builder_matches_head", source)

    @unittest.skipUnless(
        os.environ.get("R46H_RUN_P1_INTEGRATION") == "1",
        (
            "set R46H_RUN_P1_INTEGRATION=1 after a clean-HEAD modules-only v0.9 "
            "bundle exists, for the full 112 MiB Docker/mtools fixture"
        ),
    )
    def test_full_canonical_fat_image_fixture(self) -> None:
        if shutil.which("docker") is None or (shutil.which("7zz") or shutil.which("7z")) is None:
            self.skipTest("Docker or 7zz is unavailable")
        source = ROOT / "mainline/out/r46h-debian13-new-card-31719424000-v0.1/boot-p1-v0.8.img"
        if not source.is_file():
            self.skipTest("canonical v0.8 full p1 fixture is unavailable")
        with tempfile.TemporaryDirectory(prefix="r46h-v09-p1-integration.", dir=CACHE) as temporary:
            parent = Path(temporary)
            output = builder.build_candidate(ROOT, source, parent, "candidate")
            status = json.loads((output / "BUILD-STATUS.json").read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "BUILD_COMPLETE")
            self.assertTrue(status["active_boot_ini_unchanged"])
            self.assertEqual(status["changed_preexisting_files"], [])
            self.assertGreaterEqual(status["free_bytes"], 512 * 1024)
            self.assertEqual((output / builder.OUTPUT_IMAGE_NAME).stat().st_size, builder.P1_SIZE)
            repeated = builder.build_candidate(ROOT, source, parent, "candidate-repeat")
            self.assertEqual(
                builder.sha256_file(output / builder.OUTPUT_IMAGE_NAME),
                builder.sha256_file(repeated / builder.OUTPUT_IMAGE_NAME),
            )


if __name__ == "__main__":
    unittest.main()
