#!/usr/bin/env python3
"""Focused host gates for the rollback-safe R46H v0.17 BOOT promotion."""

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
PROMOTION = REPO / "mainline/gaming-product-v17-boot-promotion"
BOOT = PROMOTION / "boot.ini.v0.17-power-settle"
README = PROMOTION / "README.md"
V16_INSTALLER = REPO / "mainline/gaming-product-v16-boot-promotion/install.sh"
V16_TRANSACTION = REPO / "mainline/gaming-product-v16-boot-promotion/transaction.sh"
FROZEN_CANDIDATE = (
    REPO
    / "mainline/out/r46h-v17-mmc-power-settle"
    / "r46h-v17-mmc-power-settle.tar.gz"
)

BASE_TEST_PATH = REPO / "mainline/tests/test-r46h-v16-boot-promotion.py"
BASE_TEST_SPEC = importlib.util.spec_from_file_location(
    "r46h_v16_boot_promotion_tests", BASE_TEST_PATH
)
assert BASE_TEST_SPEC is not None and BASE_TEST_SPEC.loader is not None
BASE_TEST = importlib.util.module_from_spec(BASE_TEST_SPEC)
BASE_TEST_SPEC.loader.exec_module(BASE_TEST)

BUILDER_PATH = REPO / "mainline/scripts/build-r46h-v17-boot-promotion.py"
BUILDER_SPEC = importlib.util.spec_from_file_location(
    "r46h_v17_boot_promotion_builder", BUILDER_PATH
)
assert BUILDER_SPEC is not None and BUILDER_SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(BUILDER_SPEC)
BUILDER_SPEC.loader.exec_module(BUILDER)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def rendered(relative: str, source: Path) -> bytes:
    return BUILDER.render_payload_source(relative, source.read_bytes())


class V17PromotionFixture(BASE_TEST.PromotionFixture):
    BASE_NAMES = BASE_TEST.PromotionFixture.BASE_NAMES | {
        "boot.ini.v0.16-disable-secondary",
        "rk3326-r46h-mainline-v0.16-disable-secondary.dtb",
    }

    def __init__(self, parent: Path) -> None:
        super().__init__(parent)
        self.bytes.update(
            {
                "R46H_V17_BOOT": b"fixture-v17-boot\n",
                "R46H_V17_DTB": b"fixture-v17-dtb\n",
            }
        )
        (self.boot / "boot.ini.v0.16-disable-secondary").write_bytes(
            self.bytes["R46H_V16_BOOT"]
        )
        (self.boot / "rk3326-r46h-mainline-v0.16-disable-secondary.dtb").write_bytes(
            self.bytes["R46H_V16_DTB"]
        )
        (self.source / "boot.ini.v0.16-disable-secondary").unlink()
        (self.source / "rk3326-r46h-mainline-v0.16-disable-secondary.dtb").unlink()
        (self.source / "boot.ini.v0.17-power-settle").write_bytes(
            self.bytes["R46H_V17_BOOT"]
        )
        (self.source / "rk3326-r46h-mainline-v0.17-power-settle.dtb").write_bytes(
            self.bytes["R46H_V17_DTB"]
        )
        self.transaction.write_text(self._render_v17_transaction(), encoding="utf-8")

    def _render_v17_transaction(self) -> str:
        text = rendered(BUILDER.BASE.TRANSACTION_RELATIVE, V16_TRANSACTION).decode()
        payloads = {
            "R46H_V08_BOOT": self.bytes["R46H_V08_BOOT"],
            "R46H_V08_IMAGE": self.bytes["R46H_V08_IMAGE"],
            "R46H_V08_DTB": self.bytes["R46H_V08_DTB"],
            "R46H_V10_BOOT": self.bytes["R46H_V10_BOOT"],
            "R46H_V10_IMAGE": self.bytes["R46H_V10_IMAGE"],
            "R46H_V10_DTB": self.bytes["R46H_V10_DTB"],
            "R46H_V15_BOOT": self.bytes["R46H_V15_BOOT"],
            "R46H_V15_IMAGE": self.bytes["R46H_V15_IMAGE"],
            "R46H_V15_DTB": self.bytes["R46H_V15_DTB"],
            "R46H_V17_BOOT": self.bytes["R46H_V17_BOOT"],
            "R46H_V17_DTB": self.bytes["R46H_V17_DTB"],
            "R46H_PREVIOUS_V16_BOOT": self.bytes["R46H_V16_BOOT"],
            "R46H_PREVIOUS_V16_DTB": self.bytes["R46H_V16_DTB"],
            "R46H_UBOOT_DTB": self.bytes["R46H_UBOOT_DTB"],
        }
        replacements: dict[str, str | int] = {"R46H_MINIMUM_FREE_BYTES": 0}
        for prefix, payload in payloads.items():
            replacements[f"{prefix}_SIZE"] = len(payload)
            replacements[f"{prefix}_SHA256"] = digest(payload)
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


class R46HV17BootPromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cache = REPO / "mainline/out/.cache/r46h-v17-boot-promotion-tests"
        cls.cache.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.cache)

    def setUp(self) -> None:
        self.fixture = V17PromotionFixture(self.cache)

    def tearDown(self) -> None:
        self.fixture.close()

    def test_exact_boot_script_and_accepted_candidate(self) -> None:
        boot = BOOT.read_bytes()
        self.assertEqual(len(boot), 1_417)
        self.assertEqual(
            digest(boot),
            "96300e2e74fa3ea00da28d81c80c7fa3e327bd4784af6ddc766817b36ad33778",
        )
        text = boot.decode("utf-8")
        self.assertIn("Image.mainline-v0.15-gaming-product.gz", text)
        self.assertIn("rk3326-r46h-mainline-v0.17-power-settle.dtb", text)
        self.assertIn("0xe3bde2", text)
        self.assertIn("0x27a5200", text)
        self.assertIn("0xc199", text)
        self.assertNotIn("saveenv", text)

        self.assertEqual(FROZEN_CANDIDATE.stat().st_size, 12_517)
        self.assertEqual(
            digest(FROZEN_CANDIDATE.read_bytes()),
            "02b6da57c039c31a95143eab1b922c14c0ac4bc60621d02dab9d07f1796409a9",
        )
        with tarfile.open(FROZEN_CANDIDATE, "r:gz") as archive:
            stream = archive.extractfile("v0.17-800ms-single-host/R46H.DTB")
            self.assertIsNotNone(stream)
            candidate = stream.read()
        self.assertEqual(len(candidate), 49_561)
        self.assertEqual(
            digest(candidate),
            "116942e7bc8691bbf6bf185dd3cbe306de2d33be8dad79a027249f9f5234b796",
        )

    def test_prepare_activate_rollback_preserves_v16_predecessors(self) -> None:
        self.fixture.run(
            """
[[ "$(r46h_tx_detect_state "$boot")" == base ]]
r46h_tx_prepare "$boot" "$source_dir" 0
[[ "$(r46h_tx_detect_state "$boot")" == prepared ]]
cmp -s "$boot/boot.ini" "$boot/boot.ini.v0.15-gaming-product"
r46h_tx_activate "$boot" 0
[[ "$(r46h_tx_detect_state "$boot")" == activated ]]
cmp -s "$boot/boot.ini" "$boot/boot.ini.v0.17-power-settle"
r46h_tx_rollback "$boot"
[[ "$(r46h_tx_detect_state "$boot")" == prepared ]]
cmp -s "$boot/boot.ini" "$boot/boot.ini.v0.15-gaming-product"
cmp -s "$boot/boot.ini.v0.16-disable-secondary" <(printf 'fixture-v16-boot\n')
cmp -s "$boot/rk3326-r46h-mainline-v0.16-disable-secondary.dtb" <(printf 'fixture-v16-dtb\n')
"""
        )

    def test_activation_fault_rolls_back_to_exact_v15(self) -> None:
        self.fixture.run(
            """
r46h_tx_prepare "$boot" "$source_dir" 0
export R46H_TRANSACTION_FAULT=after-active
if r46h_tx_activate "$boot" 0; then exit 92; fi
[[ "$(r46h_tx_detect_state "$boot")" == activate-partial-v17 ]]
unset R46H_TRANSACTION_FAULT
r46h_tx_rollback "$boot"
[[ "$(r46h_tx_detect_state "$boot")" == prepared ]]
cmp -s "$boot/boot.ini" "$boot/boot.ini.v0.15-gaming-product"
"""
        )

    def test_prepare_faults_keep_v15_active_and_preserve_v16(self) -> None:
        fixtures = [self.fixture]
        try:
            for index, fault in enumerate(("after-dtb", "after-boot")):
                fixture = self.fixture if index == 0 else V17PromotionFixture(self.cache)
                if index:
                    fixtures.append(fixture)
                with self.subTest(fault=fault):
                    fixture.run(
                        f"""
export R46H_TRANSACTION_FAULT={fault}
if r46h_tx_prepare "$boot" "$source_dir" 0; then exit 91; fi
[[ "$(r46h_tx_detect_state "$boot")" == prepare-partial ]]
cmp -s "$boot/boot.ini" "$boot/boot.ini.v0.15-gaming-product"
cmp -s "$boot/boot.ini.v0.16-disable-secondary" <(printf 'fixture-v16-boot\n')
unset R46H_TRANSACTION_FAULT
r46h_tx_prepare "$boot" "$source_dir" 1
[[ "$(r46h_tx_detect_state "$boot")" == prepared ]]
"""
                    )
        finally:
            for fixture in fixtures[1:]:
                fixture.close()

    def test_rollback_fault_leaves_recoverable_v15_state(self) -> None:
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
cmp -s "$boot/boot.ini.v0.16-disable-secondary" <(printf 'fixture-v16-boot\n')
"""
        )

    def test_tampered_predecessor_and_unknown_entry_fail_closed(self) -> None:
        variants: list[Path] = []
        try:
            for mutation in ("predecessor", "extra"):
                clone = self.fixture.root.parent / f"{self.fixture.root.name}-{mutation}"
                shutil.copytree(self.fixture.root, clone)
                variants.append(clone)
                boot = clone / "boot"
                if mutation == "predecessor":
                    (boot / "boot.ini.v0.16-disable-secondary").write_bytes(b"tampered\n")
                else:
                    (boot / "unexpected.bin").write_bytes(b"unexpected\n")
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

    def test_rendered_installer_and_transaction_pin_v17_contract(self) -> None:
        installer = rendered(BUILDER.BASE.INSTALL_RELATIVE, V16_INSTALLER).decode()
        transaction = rendered(
            BUILDER.BASE.TRANSACTION_RELATIVE, V16_TRANSACTION
        ).decode()
        self.assertIn("EXPECTED_BASE_P1_SHA256=7d319785", installer)
        self.assertIn("PAYLOAD_ID=r46h-v17-boot-promotion-v0.1", installer)
        self.assertIn("prepare-v0.17-keep-v0.15-active", installer)
        self.assertIn("activate-v0.17-keep-v0.15-v0.10-v0.8", installer)
        self.assertIn("post-power-on-delay-ms", installer)
        self.assertIn("00000320", installer)
        self.assertIn("readonly R46H_BASE_TOP_LEVEL_COUNT=31", transaction)
        self.assertIn("readonly R46H_V17_DTB_SIZE=49561", transaction)
        self.assertIn(
            "readonly R46H_PREVIOUS_V16_DTB_SHA256="
            "7831617d4003cdbb2733433781f80625cb94e7c9d619f2f90990223b8f8d7f81",
            transaction,
        )
        self.assertIn(
            "readonly R46H_PREVIOUS_V16_BOOT_SHA256="
            "edb33de5fef23b810deec13c05b6958a72eea3dbb74ce2b39b0f80cdb508aba3",
            transaction,
        )
        for text in (installer, transaction):
            for line in text.splitlines():
                self.assertFalse(re.match(r"^\s*saveenv(?:\s|$)", line))
        for source, payload in (
            (V16_INSTALLER, installer.encode()),
            (V16_TRANSACTION, transaction.encode()),
        ):
            result = subprocess.run(
                ["/bin/bash", "-n"],
                input=payload,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{source}: {result.stderr.decode()}")

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
        finally:
            shutil.rmtree(work)

    def test_runbook_keeps_evidence_levels_and_completed_gate_explicit(self) -> None:
        text = " ".join(README.read_text(encoding="utf-8").split())
        self.assertIn(
            "HOST ARTIFACT + TARGET TRANSACTION + PERSISTENT COLD PASS / "
            "FIRST FUNCTIONAL VERSION ACCEPTED / STATISTICAL RELIABILITY OPEN",
            text,
        )
        self.assertNotIn("PERSISTENT COLD GATE PENDING", text)
        self.assertIn(
            "7d3197852284c7feaf0034489310cbe4eb14cb73f79b4b94b733b1cac004a18e",
            text,
        )
        self.assertIn("821.662 ms", text)
        self.assertIn("896.044 ms", text)
        self.assertIn("Standing user authority covers R46H device writes", text)
        self.assertIn("autoboot was not interrupted and Reset was not pressed", text)
        self.assertIn("819.113 ms", text)
        self.assertIn("902.528 ms", text)
        self.assertIn("qualifies the first functional version", text)
        self.assertIn("does not establish statistical cold-boot reliability", text)
        self.assertIn("build-622cf60feab7-c2eea1243359", text)
        self.assertIn(
            "c2eea1243359c06bbb9463b114b37eb52b78f0d10e01960a69b72ecc30e2ce61",
            text,
        )
        self.assertIn("two complete generations matched byte-for-byte", text)
        self.assertIn("state=base status=absent", text)
        self.assertIn(
            "da4c4607982c366ecba0e81b474b74722724de919c6a889367218507d3d17ab5",
            text,
        )
        self.assertIn(
            "ad71f67bfb436cc480bb9a83db770f88cdcadc54612b322d9106befa0982929b",
            text,
        )
        self.assertIn(
            "ffb379cf30fecfea1b3c18b20cc3685c0cd55841f21e49b6838e851d594d81b1",
            text,
        )
        self.assertIn(
            "a9a0a7aedbdbb814d14157ac19395ce48a7f71e009d2ee74fae8e16e3c6196c1",
            text,
        )
        self.assertIn(
            "3b4265849e446ee8566e47fbfb7d7ee4145bdd0d732caa7b5913684b4e4d3034",
            text,
        )
        self.assertIn(
            "c84dccd4bff90421c8a4741ebf5598b9ea7f86e619cb22212fefa6615ee97f70",
            text,
        )
        self.assertIn("The board is off with active v0.17 selected", text)


if __name__ == "__main__":
    unittest.main()
