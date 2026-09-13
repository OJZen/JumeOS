#!/usr/bin/env python3
"""Focused host gates for the rollback-safe R46H v0.16 BOOT promotion."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
PROMOTION = REPO / "mainline/gaming-product-v16-boot-promotion"
TRANSACTION = PROMOTION / "transaction.sh"
INSTALLER = PROMOTION / "install.sh"
BOOT = PROMOTION / "boot.ini.v0.16-disable-secondary"
README = PROMOTION / "README.md"
FROZEN_CANDIDATE = (
    REPO
    / "mainline/out/r46h-v16-mmc-cold-isolation"
    / "r46h-v16-mmc-cold-isolation.tar.gz"
)
BUILDER_PATH = REPO / "mainline/scripts/build-r46h-v16-boot-promotion.py"
SPEC = importlib.util.spec_from_file_location("r46h_v16_boot_builder", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class PromotionFixture:
    BASE_NAMES = {
        ".Spotlight-V100",
        ".fseventsd",
        ".console",
        "Image",
        "Image.mainline-v0.10-adc-full-range.gz",
        "Image.mainline-v0.15-gaming-product.gz",
        "Image.mainline-v0.8-bootloader-handoff.gz",
        "System Volume Information",
        "USE_DTB_SELECT_TO_SELECT_DEVICE",
        "arkos4clone-uboot.dtb",
        "boot.ini",
        "boot.ini.v0.10-adc-full-range",
        "boot.ini.v0.15-gaming-product",
        "boot.ini.v0.8-bootloader-handoff",
        "boot.ini.vendor",
        "boot.log",
        "clone_log.txt",
        "consoles",
        "dtb_selector_linux32",
        "dtb_selector_macos",
        "dtb_selector_win32.exe",
        "error.log",
        "firstboot.sh",
        "logo.bmp",
        "rk3326-r46h-linux.dtb",
        "rk3326-r46h-mainline-v0.10-adc-full-range.dtb",
        "rk3326-r46h-mainline-v0.15-gaming-product.dtb",
        "rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb",
        "uInitrd",
    }

    def __init__(self, parent: Path) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="fixture.", dir=parent))
        self.boot = self.root / "boot"
        self.source = self.root / "source"
        self.boot.mkdir()
        self.source.mkdir()
        self.bytes = {
            "R46H_V08_BOOT": b"fixture-v08-boot\n",
            "R46H_V08_IMAGE": b"fixture-v08-image\n",
            "R46H_V08_DTB": b"fixture-v08-dtb\n",
            "R46H_V10_BOOT": b"fixture-v10-boot\n",
            "R46H_V10_IMAGE": b"fixture-v10-image\n",
            "R46H_V10_DTB": b"fixture-v10-dtb\n",
            "R46H_V15_BOOT": b"fixture-v15-boot\n",
            "R46H_V15_IMAGE": b"fixture-v15-image\n",
            "R46H_V15_DTB": b"fixture-v15-dtb\n",
            "R46H_V16_BOOT": b"fixture-v16-boot\n",
            "R46H_V16_DTB": b"fixture-v16-dtb\n",
            "R46H_UBOOT_DTB": b"fixture-uboot-dtb\n",
        }
        directories = {
            "consoles",
            "System Volume Information",
            ".Spotlight-V100",
            ".fseventsd",
        }
        for name in sorted(self.BASE_NAMES):
            path = self.boot / name
            if name in directories:
                path.mkdir()
            else:
                path.write_bytes(f"legacy:{name}\n".encode())
        (self.boot / "consoles/r46h").mkdir()
        (self.boot / ".fseventsd/fseventsd-uuid").write_bytes(b"fixture-volume-id\n")
        (self.boot / ".fseventsd/0000000000000001").write_bytes(
            b"fixture-event-record\n"
        )
        mapping = {
            "boot.ini.v0.8-bootloader-handoff": "R46H_V08_BOOT",
            "Image.mainline-v0.8-bootloader-handoff.gz": "R46H_V08_IMAGE",
            "rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb": "R46H_V08_DTB",
            "boot.ini.v0.10-adc-full-range": "R46H_V10_BOOT",
            "Image.mainline-v0.10-adc-full-range.gz": "R46H_V10_IMAGE",
            "rk3326-r46h-mainline-v0.10-adc-full-range.dtb": "R46H_V10_DTB",
            "boot.ini.v0.15-gaming-product": "R46H_V15_BOOT",
            "Image.mainline-v0.15-gaming-product.gz": "R46H_V15_IMAGE",
            "rk3326-r46h-mainline-v0.15-gaming-product.dtb": "R46H_V15_DTB",
            "boot.ini": "R46H_V15_BOOT",
            "arkos4clone-uboot.dtb": "R46H_UBOOT_DTB",
        }
        for name, key in mapping.items():
            (self.boot / name).write_bytes(self.bytes[key])
        (self.boot / "consoles/r46h/arkos4clone-uboot.dtb").write_bytes(
            self.bytes["R46H_UBOOT_DTB"]
        )
        (self.source / "boot.ini.v0.16-disable-secondary").write_bytes(
            self.bytes["R46H_V16_BOOT"]
        )
        (self.source / "rk3326-r46h-mainline-v0.16-disable-secondary.dtb").write_bytes(
            self.bytes["R46H_V16_DTB"]
        )
        self.transaction = self.root / "transaction.sh"
        self.transaction.write_text(self._render_transaction(), encoding="utf-8")

    def _render_transaction(self) -> str:
        text = TRANSACTION.read_text(encoding="utf-8")
        replacements: dict[str, str | int] = {}
        for prefix in (
            "R46H_V08_BOOT",
            "R46H_V08_IMAGE",
            "R46H_V08_DTB",
            "R46H_V10_BOOT",
            "R46H_V10_IMAGE",
            "R46H_V10_DTB",
            "R46H_V15_BOOT",
            "R46H_V15_IMAGE",
            "R46H_V15_DTB",
            "R46H_V16_BOOT",
            "R46H_V16_DTB",
            "R46H_UBOOT_DTB",
        ):
            replacements[f"{prefix}_SIZE"] = len(self.bytes[prefix])
            replacements[f"{prefix}_SHA256"] = digest(self.bytes[prefix])
        replacements["R46H_MINIMUM_FREE_BYTES"] = 0
        for name, value in replacements.items():
            text, count = re.subn(
                rf"^readonly {re.escape(name)}=.*$",
                f"readonly {name}={value}",
                text,
                count=1,
                flags=re.MULTILINE,
            )
            if count != 1:
                raise AssertionError(f"cannot render fixture constant {name}")
        return text

    def run(self, commands: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["/bin/bash"],
            input=f"""
set -Eeuo pipefail
export R46H_TRANSACTION_TEST_MODE=1
source {self.transaction}
boot={self.boot}
source_dir={self.source}
{commands}
""",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            cwd=REPO,
        )
        if result.returncode != 0:
            raise AssertionError(
                f"fixture command failed with {result.returncode}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def close(self) -> None:
        shutil.rmtree(self.root)


class R46HV16BootPromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cache = REPO / "mainline/out/.cache/r46h-v16-boot-promotion-tests"
        cls.cache.mkdir(parents=True, exist_ok=True)

    def setUp(self) -> None:
        self.fixture = PromotionFixture(self.cache)

    def tearDown(self) -> None:
        self.fixture.close()

    def test_boot_script_and_candidate_are_the_accepted_exact_pair(self) -> None:
        boot = BOOT.read_bytes()
        self.assertEqual(len(boot), 1_449)
        self.assertEqual(
            digest(boot),
            "edb33de5fef23b810deec13c05b6958a72eea3dbb74ce2b39b0f80cdb508aba3",
        )
        text = boot.decode("utf-8")
        self.assertIn("Image.mainline-v0.15-gaming-product.gz", text)
        self.assertIn("rk3326-r46h-mainline-v0.16-disable-secondary.dtb", text)
        self.assertIn("0xe3bde2", text)
        self.assertIn("0x27a5200", text)
        self.assertIn("0xc172", text)
        self.assertNotIn("saveenv", text)

        self.assertEqual(FROZEN_CANDIDATE.stat().st_size, 12_466)
        self.assertEqual(
            digest(FROZEN_CANDIDATE.read_bytes()),
            "e9d04016f03e5619c64c3a8916b361c64857a6928cbf99f43392492c3d5276d1",
        )
        with tarfile.open(FROZEN_CANDIDATE, "r:gz") as archive:
            stream = archive.extractfile("v0.16-disable-secondary/R46H.DTB")
            self.assertIsNotNone(stream)
            candidate = stream.read()
        self.assertEqual(len(candidate), 49_522)
        self.assertEqual(
            digest(candidate),
            "7831617d4003cdbb2733433781f80625cb94e7c9d619f2f90990223b8f8d7f81",
        )

    def test_happy_prepare_activate_and_rollback(self) -> None:
        metadata_before = {
            path.relative_to(self.fixture.boot).as_posix(): path.read_bytes()
            for path in (self.fixture.boot / ".fseventsd").iterdir()
        }
        self.fixture.run(
            """
[[ "$(r46h_tx_detect_state "$boot")" == base ]]
r46h_tx_prepare "$boot" "$source_dir" 0
[[ "$(r46h_tx_detect_state "$boot")" == prepared ]]
cmp -s "$boot/boot.ini" "$boot/boot.ini.v0.15-gaming-product"
r46h_tx_activate "$boot" 0
[[ "$(r46h_tx_detect_state "$boot")" == activated ]]
cmp -s "$boot/boot.ini" "$boot/boot.ini.v0.16-disable-secondary"
r46h_tx_rollback "$boot"
[[ "$(r46h_tx_detect_state "$boot")" == prepared ]]
cmp -s "$boot/boot.ini" "$boot/boot.ini.v0.15-gaming-product"
cmp -s "$boot/boot.ini.v0.10-adc-full-range" <(printf 'fixture-v10-boot\n')
cmp -s "$boot/boot.ini.v0.8-bootloader-handoff" <(printf 'fixture-v08-boot\n')
"""
        )
        metadata_after = {
            path.relative_to(self.fixture.boot).as_posix(): path.read_bytes()
            for path in (self.fixture.boot / ".fseventsd").iterdir()
        }
        self.assertEqual(metadata_after, metadata_before)

    def test_prepare_faults_keep_v15_active_and_recover(self) -> None:
        fixtures = [self.fixture]
        try:
            for index, fault in enumerate(("after-dtb", "after-boot")):
                fixture = self.fixture if index == 0 else PromotionFixture(self.cache)
                if index:
                    fixtures.append(fixture)
                with self.subTest(fault=fault):
                    fixture.run(
                        f"""
export R46H_TRANSACTION_FAULT={fault}
if r46h_tx_prepare "$boot" "$source_dir" 0; then exit 91; fi
[[ "$(r46h_tx_detect_state "$boot")" == prepare-partial ]]
cmp -s "$boot/boot.ini" "$boot/boot.ini.v0.15-gaming-product"
unset R46H_TRANSACTION_FAULT
r46h_tx_prepare "$boot" "$source_dir" 1
[[ "$(r46h_tx_detect_state "$boot")" == prepared ]]
"""
                    )
        finally:
            for fixture in fixtures[1:]:
                fixture.close()

    def test_activation_fault_can_recover_or_restore_v15(self) -> None:
        self.fixture.run(
            """
r46h_tx_prepare "$boot" "$source_dir" 0
export R46H_TRANSACTION_FAULT=after-active
if r46h_tx_activate "$boot" 0; then exit 92; fi
[[ "$(r46h_tx_detect_state "$boot")" == activate-partial-v16 ]]
unset R46H_TRANSACTION_FAULT
r46h_tx_rollback "$boot"
[[ "$(r46h_tx_detect_state "$boot")" == prepared ]]
cmp -s "$boot/boot.ini" "$boot/boot.ini.v0.15-gaming-product"
r46h_tx_activate "$boot" 0
[[ "$(r46h_tx_detect_state "$boot")" == activated ]]
"""
        )

    def test_rollback_fault_leaves_an_exact_recoverable_state(self) -> None:
        self.fixture.run(
            """
r46h_tx_prepare "$boot" "$source_dir" 0
r46h_tx_activate "$boot" 0
export R46H_TRANSACTION_FAULT=after-rollback-active
if r46h_tx_rollback "$boot"; then exit 93; fi
[[ "$(r46h_tx_detect_state "$boot")" == rollback-partial-v15 ]]
unset R46H_TRANSACTION_FAULT
r46h_tx_rollback "$boot"
[[ "$(r46h_tx_detect_state "$boot")" == prepared ]]
cmp -s "$boot/boot.ini" "$boot/boot.ini.v0.15-gaming-product"
"""
        )

    def test_tampered_anchor_extra_entry_and_symlink_fail_closed(self) -> None:
        variants: list[Path] = []
        try:
            for mutation in ("anchor", "extra", "symlink", "metadata-type"):
                clone = self.fixture.root.parent / f"{self.fixture.root.name}-{mutation}"
                shutil.copytree(self.fixture.root, clone)
                variants.append(clone)
                boot = clone / "boot"
                if mutation == "anchor":
                    (boot / "boot.ini.v0.10-adc-full-range").write_bytes(b"tampered\n")
                elif mutation == "extra":
                    (boot / "unexpected.bin").write_bytes(b"unexpected\n")
                else:
                    if mutation == "symlink":
                        target = boot / "boot.ini.v0.15-gaming-product"
                        target.unlink()
                        target.symlink_to("boot.ini")
                    else:
                        shutil.rmtree(boot / ".fseventsd")
                        (boot / ".fseventsd").write_bytes(b"unsafe metadata type\n")
                result = subprocess.run(
                    [
                        "/bin/bash",
                        "-c",
                        f"export R46H_TRANSACTION_TEST_MODE=1; "
                        f"source {clone / 'transaction.sh'}; r46h_tx_detect_state {boot}",
                    ],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    cwd=REPO,
                )
                self.assertNotEqual(result.returncode, 0, mutation)
        finally:
            for clone in variants:
                shutil.rmtree(clone)

    def test_installer_pins_identity_recovery_and_cold_postflight(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("EXPECTED_BASE_P1_SHA256=042ad4ad", text)
        self.assertIn("EXPECTED_PREFIX_SHA256=3fe2feb9", text)
        self.assertIn("/dev/disk/by-partuuid/$EXPECTED_BOOT_PARTUUID", text)
        self.assertIn("R46H_BOOT_DEVICE=$BOOT_DEVICE", text)
        self.assertIn("require_identity \"$payload/install.sh\" 500", text)
        self.assertIn("STATUS_STATE=retention-partial", text)
        self.assertIn("activation must use the checksum-bound retained payload", text)
        self.assertIn("payload_sha256s_sha256=$(payload_manifest_hash)", text)
        self.assertIn("transaction test environment is forbidden", text)
        self.assertNotIn("$(inspect_boot)", text)
        self.assertIn("BOOT_STATE=$(r46h_tx_detect_state", text)
        self.assertIn("/proc/device-tree/mmc@ff380000/status", text)
        self.assertIn("persistent v0.16 cold gate requires clean MMC initialization", text)
        self.assertIn("Timeout waiting for hardware cmd interrupt", text)
        self.assertIn("ROMS became mounted", text)
        self.assertIn('r46h_mod_verify_tree "$MODULES_PARENT" installed', text)
        self.assertNotIn("V15_STATUS", text)
        cleanup = text[text.index("cleanup()") : text.index("begin_write()")]
        self.assertIn("if umount \"$BOOT_MOUNT\"; then", cleanup)
        self.assertIn("can_remove_work=0", cleanup)
        self.assertIn("work directory contains a mount; cleanup was refused", cleanup)
        postflight = text[text.index("perform_postflight()") : text.index("discover_devices\n")]
        self.assertLess(postflight.index("verify_runtime_health"), postflight.index("write_status complete"))
        for line in text.splitlines():
            stripped = line.strip()
            self.assertFalse(re.match(r"^(sudo +)?(reboot|poweroff)( |$)", stripped))
            self.assertFalse(re.match(r"^saveenv( |$)", stripped))

    def test_production_flush_uses_the_installer_bound_boot_device(self) -> None:
        trace = self.fixture.root / "blockdev.trace"
        result = subprocess.run(
            ["/bin/bash"],
            input=(
                "set -Eeuo pipefail\n"
                f"source {TRANSACTION}\n"
                "sync() { :; }\n"
                f"blockdev() {{ printf '%s\\n' \"$*\" > {trace}; }}\n"
                "BOOT_DEVICE=/dev/disk/by-partuuid/r46h-test-boot\n"
                "R46H_BOOT_DEVICE=$BOOT_DEVICE\n"
                "r46h_tx_flush\n"
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            cwd=REPO,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            trace.read_text(encoding="utf-8"),
            "--flushbufs /dev/disk/by-partuuid/r46h-test-boot\n",
        )

    def test_builder_payload_is_self_checking_and_deterministic(self) -> None:
        captured = {
            relative: (REPO / relative).read_bytes() for relative in BUILDER.SOURCE_PATHS
        }
        candidate = BUILDER.read_frozen_candidate()
        BUILDER.check_script_constants(captured, candidate)
        work = Path(tempfile.mkdtemp(prefix="builder.", dir=self.cache))
        try:
            payload = work / "payload"
            BUILDER.create_payload(payload, captured, candidate, "a" * 40, "b" * 40)
            check = subprocess.run(
                [str(payload / "install.sh"), "--check-payload"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                cwd=REPO,
            )
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertIn("payload structure and checksums validated", check.stdout)
            first = BUILDER.deterministic_archive(payload)
            second = BUILDER.deterministic_archive(payload)
            self.assertEqual(first, second)
            observed = BUILDER.validate_archive(first)
            self.assertEqual(
                digest(observed[f"files/{BUILDER.CANDIDATE_DTB_NAME}"]),
                BUILDER.CANDIDATE_DTB_SHA256,
            )
            self.assertEqual(
                digest(observed[f"files/{BUILDER.BOOT_NAME}"]),
                BUILDER.BOOT_SHA256,
            )
            rootfs = BUILDER.verify_v05_rootfs_contract()
            self.assertEqual(rootfs["module_trees"], BUILDER.MODULE_TREE_SHA256)
            self.assertEqual(
                rootfs["old_v15_promotion_state"],
                "absent-after-full-p2-rewrite",
            )
        finally:
            shutil.rmtree(work)

    def test_shell_scripts_have_valid_bash_syntax(self) -> None:
        for script in (TRANSACTION, INSTALLER):
            with self.subTest(script=script.name):
                result = subprocess.run(
                    ["/bin/bash", "-n", str(script)],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    cwd=REPO,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_runbook_records_corrected_generation_failed_gate_and_rollback(self) -> None:
        text = " ".join(README.read_text(encoding="utf-8").split())
        self.assertIn(
            "HOST ARTIFACT PASS / PERSISTENT COLD GATE FAIL / "
            "EXACT V0.15 ROLLBACK PASS",
            text,
        )
        self.assertIn("e47adf35182ed5a163bb08296e08b7642c50b766", text)
        self.assertIn(
            "f02155890d825166a07f2e06d145d8bbb9841f73d3ea11f32c0841831f05313a",
            text,
        )
        self.assertIn("29,094-byte archive", text)
        self.assertIn("but it is now revoked", text)
        self.assertIn("unexpected BOOT top-level entry: .fseventsd", text)
        self.assertIn("before any p1 write", text)
        self.assertIn("twenty-ninth required base entry", text)
        self.assertIn("Second review revoked it before any transfer or target write", text)
        self.assertIn("superseded generation directory was deleted", text)
        self.assertIn("408baa52f95d1c66c321ccc820a4481cb7ac2266", text)
        self.assertIn("build-408baa52f95d-99d162b5d920", text)
        self.assertIn(
            "99d162b5d920f14108d9d7ff725f96f3e0e52d20dbd713fac46a4a53023ad042",
            text,
        )
        self.assertIn("29,123-byte archive", text)
        self.assertIn("persistent v0.16 boot contains a forbidden storage marker", text)
        self.assertIn("status=rollback-complete", text)
        self.assertIn(
            "7d3197852284c7feaf0034489310cbe4eb14cb73f79b4b94b733b1cac004a18e",
            text,
        )
        self.assertIn(
            "895a2ebaca0ec88f936d53142009716b80d99d72ee9214b2afdd1245d8b703b1",
            text,
        )
        self.assertNotIn("TARGET WRITE NOT AUTHORIZED", text)


if __name__ == "__main__":
    unittest.main()
