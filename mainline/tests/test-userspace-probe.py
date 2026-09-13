#!/usr/bin/env python3
import hashlib
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


MAINLINE = pathlib.Path(__file__).resolve().parents[1]
SOURCE = MAINLINE / "userspace-probe"
BUILD_SCRIPT = MAINLINE / "scripts" / "build-userspace-probe.sh"
PACKAGER = MAINLINE / "scripts" / "package-userspace-probe-bundle.py"
BASELINE = MAINLINE / "deploy" / "baselines" / "v0.8-bootloader-handoff.json"
PROFILE = MAINLINE / "deploy" / "profiles" / "hl-r46h-v22-g92-v1.json"
STAGE_TEMPLATE = MAINLINE / "deploy" / "templates" / "stage-easyroms-macos.sh.in"
OUTPUT = MAINLINE / "out" / "r46h-easyroms-debian13-mesa-probe-v0.2"
PAYLOAD = OUTPUT / "payload"
IMAGE_NAME = "r46h-userspace-probe-debian13-mesa-v0.2.squashfs"
BASE_DIGEST = "020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd"


def make_packager_fixture(root_path):
    input_dir = root_path / "input"
    output_root = root_path / "output"
    input_dir.mkdir()
    output_root.mkdir()
    image = input_dir / IMAGE_NAME
    image.write_bytes(b"test-squashfs-image")
    image_sha = hashlib.sha256(image.read_bytes()).hexdigest()
    bootstrap = (SOURCE / "run-on-target.sh").read_text().replace(
        "@IMAGE_SHA256@", image_sha
    )
    (input_dir / "bootstrap-target.sh").write_text(bootstrap)
    (input_dir / "BUILD-INFO").write_text(
        "probe_id=debian13-mesa-v0.2\n"
        "architecture=arm64\n"
        "kernel_contract=6.12.99-r46h-mainline-v0.8-bootloader-handoff\n"
        "source_git_commit=0123456789abcdef0123456789abcdef01234567\n"
        "source_git_dirty=false\n"
        "source_snapshot_method=git-archive-exact-commit\n"
        "source_archive_sha256=" + "a" * 64 + "\n"
    )
    for name in (
        "LDD.txt",
        "PACKAGES.tsv",
        "PROBE-FILE.txt",
        "SQUASHFS-FILES.txt",
        "SQUASHFS-INFO.txt",
        "SOURCE-SHA256SUMS",
    ):
        (input_dir / name).write_text(f"receipt={name}\n")
    return input_dir, output_root


def packager_command(input_dir, output_root):
    return [
        sys.executable,
        str(PACKAGER),
        "--input-dir",
        str(input_dir),
        "--output-root",
        str(output_root),
        "--card-profile",
        str(PROFILE),
        "--current-baseline",
        str(BASELINE),
        "--stage-template",
        str(STAGE_TEMPLATE),
        "--source-date-epoch",
        "1785974400",
    ]


class UserspaceProbeSourceTests(unittest.TestCase):
    def test_runtime_packages_are_narrow_and_vendor_mali_free(self):
        packages = (SOURCE / "packages.txt").read_text().splitlines()
        self.assertEqual(
            packages,
            [
                "ca-certificates",
                "libdrm2",
                "libegl1",
                "libgbm1",
                "libgl1-mesa-dri",
                "libgles2",
            ],
        )
        self.assertNotIn("libmali", "\n".join(packages).lower())

    def test_container_sources_are_digest_pinned(self):
        for name in ("Dockerfile", "Squashfs.Dockerfile"):
            text = (SOURCE / name).read_text()
            self.assertIn(f"debian:trixie-slim@sha256:{BASE_DIGEST}", text)
            self.assertNotRegex(text, r"^FROM\s+debian:trixie-slim\s*$", re.MULTILINE)

    def test_probe_requires_real_mesa_panfrost_and_gpu_readback(self):
        text = (SOURCE / "r46h-gles2-fbo-probe.c").read_text()
        for marker in (
            'contains_case_insensitive(vendor, "mesa")',
            'contains_case_insensitive(renderer, "panfrost")',
            'contains_case_insensitive(renderer, "mali-g31")',
            'contains_case_insensitive(renderer, "llvmpipe")',
            'contains_case_insensitive(renderer, "softpipe")',
            'contains_case_insensitive(renderer, "swrast")',
            "glCompileShader",
            "glCheckFramebufferStatus",
            "glDrawArrays",
            "glFinish",
            "glReadPixels",
            'R46H_MESA_PROBE result=pass',
        ):
            self.assertIn(marker, text)

    def test_target_runtime_exposes_only_render_node_and_readonly_sysfs(self):
        text = (SOURCE / "run-on-target.sh").read_text()
        self.assertIn(
            "EXPECTED_KERNEL=6.12.99-r46h-mainline-v0.8-bootloader-handoff", text
        )
        self.assertIn(
            "unshare --mount --pid --fork --net --propagation private", text
        )
        self.assertIn("mount --bind /dev/dri/renderD128", text)
        self.assertNotIn("mount --bind /dev/dri/card0", text)
        self.assertNotIn("mount --bind /dev/dri/card1", text)
        self.assertIn('[[ ! -e "$R46H_PROBE_ROOT/dev/dri/card0" ]]', text)
        self.assertIn('[[ ! -e "$R46H_PROBE_ROOT/dev/dri/card1" ]]', text)
        self.assertIn(
            'mount -t sysfs -o ro,nosuid,nodev,noexec sysfs "$R46H_PROBE_ROOT/sys"',
            text,
        )
        self.assertIn(
            '[[ "$(findmnt -rn -T "$R46H_PROBE_ROOT/sys" -o FSTYPE)" == sysfs ]]',
            text,
        )
        self.assertIn(
            'sysfs_options=$(findmnt -rn -T "$R46H_PROBE_ROOT/sys" -o OPTIONS)',
            text,
        )
        for option in ("ro", "nosuid", "nodev", "noexec"):
            self.assertIn(f'[[ ",$sysfs_options," == *,{option},* ]]', text)
        self.assertNotIn('[[ -z "$(find "$R46H_PROBE_ROOT/sys"', text)
        self.assertNotIn("mount --bind /sys", text)
        self.assertNotIn("mount --rbind /sys", text)
        self.assertIn("size=128m tmpfs", text)
        self.assertIn("insufficient-memory-for-trusted-copy", text)
        self.assertIn('actual_sha=$(hash_file "$trusted_image")', text)
        self.assertNotIn("R46H_PROBE_IMAGE_FD", text)
        self.assertIn("--reuid 65534", text)
        self.assertIn("--regid \"$R46H_PROBE_RENDER_GID\"", text)
        self.assertIn("--clear-groups", text)
        self.assertIn("--no-new-privs", text)
        self.assertIn("--bounding-set=-all", text)
        self.assertIn("--inh-caps=-all", text)
        self.assertIn("--ambient-caps=-all", text)
        self.assertIn("TIMEOUT_SECONDS=30", text)
        self.assertIn("SESSION_TIMEOUT_SECONDS=45", text)
        self.assertIn(
            'timeout -s TERM -k 5 "$SESSION_TIMEOUT_SECONDS"', text
        )
        self.assertIn("MESA_LOADER_DRIVER_OVERRIDE=panfrost", text)
        self.assertNotIn("systemctl stop", text)
        self.assertIn("probe_status=$?", text)
        self.assertIn("probe_started=1", text)
        self.assertIn("if (( probe_started == 1 )); then", text)
        self.assertIn("sleep 3", text)
        self.assertIn('head -c "$before_bytes" "$after_log" | cmp -s', text)
        self.assertIn("preexisting-ext4-errors", text)
        self.assertIn('mountpoint -q -- "$trusted_root"', text)
        self.assertIn("trusted-tmpfs-remains-mounted", text)
        self.assertIn("trap 'exit 143' TERM", text)
        self.assertIn("ext4_errors_before", text)
        self.assertIn("ext4-errors-count-changed", text)
        self.assertIn("new-gpu-or-storage-fault", text)
        self.assertIn("I/O error.*mmc", text)
        self.assertIn("mmc.*(I/O error|error|timeout|CRC|fail(ed|ure)?)", text)
        self.assertIn("blk_update_request|end_request|blk_print_req_error", text)
        self.assertIn("exFAT-fs|FAT-fs", text)
        self.assertIn("warning|bug|oops|panic", text)
        self.assertIn("BUG:|Oops:|kernel panic|Call trace:|cut here", text)
        self.assertIn("fail(ed|ure)?", text)

    def test_target_requires_post_eject_receipt_and_card_commitment(self):
        text = (SOURCE / "run-on-target.sh").read_text()
        for marker in (
            "--external-receipt",
            "--external-receipt-sha256",
            "expected_receipt_keys=",
            "external-receipt-checksum-mismatch",
            "bootstrap-checksum-mismatch",
            "stage-source-list-checksum-mismatch",
            "FINAL-RECEIPT-COMMITMENT",
            "completion-secret-checksum-mismatch",
            "final-receipt-commitment-mismatch",
            "staged-payload-entry-set-mismatch",
            "trusted-stage-complete-checksum-mismatch",
        ):
            self.assertIn(marker, text)
        self.assertIn("EXPECTED_CARD_PROFILE_SHA256=", text)
        self.assertIn("EXPECTED_G92_PREFIX_SHA256=", text)
        self.assertIn("0:700", text)
        self.assertIn("0:600", text)

    def test_stager_freezes_verified_sources_before_writing(self):
        text = STAGE_TEMPLATE.read_text()
        self.assertIn("freeze_source_snapshot", text)
        self.assertIn('SOURCE_ROOT=$snapshot_payload', text)
        self.assertIn('R46H_MANIFEST="${snapshot_payload}/DEPLOY-MANIFEST"', text)
        self.assertIn('publish_source "$SOURCE_ROOT/$name"', text)
        self.assertIn("private source snapshot identity changed", text)
        self.assertIn("'%u:%Lp' \"$receipt_parent\"", text)
        self.assertIn('"$(id -u):700"', text)
        self.assertIn("R46H_DEPLOY_STAGE_TEST_WITHDRAW_SOURCE_AFTER_SNAPSHOT", text)
        self.assertIn("live source withdrawal was incomplete", text)
        self.assertIn("bootstrap_hash=$(manifest_value target_bootstrap_sha256)", text)
        self.assertNotIn('publish_source "$BUNDLE_DIR/$path"', text)
        self.assertNotIn('bootstrap_hash=$(hash_file "$SOURCE_ROOT/bootstrap-target.sh")', text)
        freeze_call = text.rindex("\nfreeze_source_snapshot\n")
        self.assertGreater(text.index("boot_number=$(manifest_value", freeze_call), freeze_call)
        self.assertGreater(text.index("payload_name=$(manifest_value", freeze_call), freeze_call)
        self.assertGreater(text.index("payload_final=", freeze_call), freeze_call)

    def test_build_forces_kernel_supported_squashfs(self):
        text = BUILD_SCRIPT.read_text()
        self.assertIn("-noappend -all-root -no-xattrs -comp gzip", text)
        self.assertIn("Compression gzip", text)
        self.assertIn("panfrost_dri.so", text)
        self.assertIn("libMali|not found", text)
        self.assertIn('sed "s/@IMAGE_SHA256@/$image_sha/"', text)
        self.assertIn("package-userspace-probe-bundle.py", text)
        frozen_message = (
            "userspace probe v0.2 build is frozen after the raw exFAT "
            "verification failure"
        )
        self.assertIn(frozen_message, text)
        self.assertLess(text.index(frozen_message), text.index("docker build"))
        self.assertIn("git -C \"$REPO_ROOT\" archive", text)
        self.assertIn("SOURCE_DIR=$SNAPSHOT_MAINLINE/userspace-probe", text)
        self.assertIn("source_snapshot_method=git-archive-exact-commit", text)
        self.assertIn('--output-root "$OUTPUT_ROOT"', text)
        self.assertGreaterEqual(text.count("assert_repository_binding"), 3)
        self.assertLess(
            text.rindex("assert_repository_binding"), text.rindex('python3 "$PACKAGER"')
        )
        self.assertNotIn("source_dirty=true", text)

    def test_v08_baseline_matches_deployed_canonical_anchors(self):
        self.assertEqual(
            hashlib.sha256(BASELINE.read_bytes()).hexdigest(),
            "065b06b94a44ef73290691cfb222f14184da6c5b2e594112a33997493f0bf8a9",
        )
        text = BASELINE.read_text()
        for marker in (
            '"release": "6.12.99-r46h-mainline-v0.8-bootloader-handoff"',
            '"candidate_sha256": "cead3fbee0d5c42fddcd6f6d83839b82af791e1abf1dd0252d9850fb47dd33fb"',
            '"image_sha256": "d7c7796c097fbe692412fb63d19c1f97c4b21f55ae2c3b1e8df324a739f166fa"',
            '"sha256": "7f824b5cabc1a1d6bee540fe56a95e4b32128ec5d603784f8a0a363117152bb5"',
        ):
            self.assertIn(marker, text)

    def test_packager_refuses_to_republish_the_frozen_v02_identity(self):
        cache = MAINLINE / "out" / ".cache"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".probe-packager-test.", dir=cache) as root:
            root_path = pathlib.Path(root)
            input_dir, output_root = make_packager_fixture(root_path)

            result = subprocess.run(
                packager_command(input_dir, output_root),
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("PASS:", result.stdout)
            self.assertIn(
                "userspace probe v0.2 repackaging is frozen after the raw exFAT "
                "verification failure",
                result.stderr,
            )
            self.assertEqual(list(output_root.iterdir()), [])

    def test_packager_rejects_mismatched_bootstrap_identity(self):
        cache = MAINLINE / "out" / ".cache"
        cache.mkdir(parents=True, exist_ok=True)
        identities = {
            "PROBE_ID": "debian13-mesa-v9.9",
            "PAYLOAD_NAME": "r46h-debian13-mesa-probe-v9.9",
            "IMAGE_NAME": "r46h-userspace-probe-debian13-mesa-v9.9.squashfs",
        }
        for key, replacement in identities.items():
            with self.subTest(key=key):
                with tempfile.TemporaryDirectory(
                    prefix=".probe-packager-identity.", dir=cache
                ) as root:
                    root_path = pathlib.Path(root)
                    input_dir, output_root = make_packager_fixture(root_path)
                    bootstrap_path = input_dir / "bootstrap-target.sh"
                    bootstrap = bootstrap_path.read_text()
                    bootstrap = re.sub(
                        rf"(?m)^readonly {key}=\S+$",
                        f"readonly {key}={replacement}",
                        bootstrap,
                        count=1,
                    )
                    bootstrap_path.write_text(bootstrap)

                    result = subprocess.run(
                        packager_command(input_dir, output_root),
                        capture_output=True,
                        text=True,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn("PASS:", result.stdout)
                    self.assertIn(
                        f"bootstrap {key} identity mismatch", result.stderr
                    )
                    self.assertEqual(list(output_root.iterdir()), [])

    def test_concurrent_packagers_both_fail_before_publication(self):
        cache = MAINLINE / "out" / ".cache"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".probe-packager-race.", dir=cache) as root:
            root_path = pathlib.Path(root)
            input_dir, output_root = make_packager_fixture(root_path)
            commands = [packager_command(input_dir, output_root) for _ in range(2)]
            processes = [
                subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                for command in commands
            ]
            results = [(*process.communicate(), process.returncode) for process in processes]

            self.assertTrue(all(result[2] != 0 for result in results), results)
            for stdout, stderr, _ in results:
                self.assertNotIn("PASS:", stdout)
                self.assertIn(
                    "userspace probe v0.2 repackaging is frozen after the raw "
                    "exFAT verification failure",
                    stderr,
                )
            self.assertEqual(list(output_root.iterdir()), [])


class UserspaceProbeArtifactTests(unittest.TestCase):
    @unittest.skipUnless(OUTPUT.is_dir(), "generated probe artifact is absent")
    def test_generated_checksums_and_receipt(self):
        sums = OUTPUT / "STAGE-SOURCES.sha256"
        self.assertTrue(sums.is_file())
        for line in sums.read_text().splitlines():
            digest, name = line.split("  ", 1)
            path = OUTPUT / name
            self.assertTrue(path.is_file(), name)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

        build_info = (PAYLOAD / "BUILD-INFO").read_text()
        self.assertIn("distribution=Debian GNU/Linux 13 (trixie)", build_info)
        self.assertIn("architecture=arm64", build_info)
        self.assertIn("squashfs_compression=gzip", build_info)
        self.assertIn(
            "kernel_contract=6.12.99-r46h-mainline-v0.8-bootloader-handoff",
            build_info,
        )
        self.assertIn("source_git_dirty=false", build_info)
        self.assertIn("source_snapshot_method=git-archive-exact-commit", build_info)
        self.assertRegex(build_info, r"(?m)^source_archive_sha256=[0-9a-f]{64}$")
        self.assertNotIn("libMali", (PAYLOAD / "LDD.txt").read_text())
        self.assertNotIn("@IMAGE_SHA256@", (PAYLOAD / "bootstrap-target.sh").read_text())


if __name__ == "__main__":
    unittest.main()
