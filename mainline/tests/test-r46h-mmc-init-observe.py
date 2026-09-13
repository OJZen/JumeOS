#!/usr/bin/env python3
"""Regression gates for the R46H cold-MMC diagnostic candidate."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


MAINLINE = Path(__file__).resolve().parents[1]
REPO = MAINLINE.parent
PATCH = MAINLINE / "patches/0010-mmc-dw-log-request-errors.patch"
KERNEL_TARBALL = MAINLINE / ".cache/kernel/linux-6.12.99.tar.xz"
KERNEL_TARBALL_SHA256 = (
    "6a477222c132033381cda981eb0127f29fbcbba17e820283bc21290f8e408629"
)
DRIVER = Path("drivers/mmc/host/dw_mmc.c")
CORE = Path("drivers/mmc/core/core.c")
MANIFEST = MAINLINE / "manifest.env"
CONFIG = MAINLINE / "config/r46h.fragment"
BUILD = MAINLINE / "scripts/build-kernel.sh"
CONTAINER_BUILD = MAINLINE / "scripts/build-in-container.sh"
RUNBOOK = MAINLINE / "bringup-tests/V13-MMC-INIT-ONE-SHOT.md"
BUILD_ID = "v0.15-gaming-product"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_blob_oid(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    open_brace = source.index("{", start)
    depth = 0
    for index in range(open_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated function: {signature}")


class R46HMMCInitObserveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not KERNEL_TARBALL.is_file():
            raise unittest.SkipTest(f"missing cached kernel tarball: {KERNEL_TARBALL}")
        if file_sha256(KERNEL_TARBALL) != KERNEL_TARBALL_SHA256:
            raise AssertionError(f"kernel tarball SHA-256 mismatch: {KERNEL_TARBALL}")

        cls.patch = PATCH.read_text(encoding="utf-8")
        cls.manifest = MANIFEST.read_text(encoding="utf-8")
        cls.config = CONFIG.read_text(encoding="utf-8")
        cls.build = BUILD.read_text(encoding="utf-8")
        cls.container_build = CONTAINER_BUILD.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="r46h-mmc-init-observe.", dir=MAINLINE / ".cache"
        )
        cls.root = Path(cls.temporary.name)
        cls.source = cls.root / "linux-6.12.99"
        members = [
            f"linux-6.12.99/{DRIVER}",
            f"linux-6.12.99/{CORE}",
        ]
        subprocess.run(
            ["tar", "-xJf", str(KERNEL_TARBALL), "-C", str(cls.root), *members],
            check=True,
        )
        cls.before = (cls.source / DRIVER).read_bytes()
        with PATCH.open("rb") as patch_input:
            subprocess.run(
                ["patch", "--directory", str(cls.source), "--strip=1", "--forward"],
                stdin=patch_input,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        cls.after = (cls.source / DRIVER).read_bytes()
        cls.driver = cls.after.decode("utf-8")
        cls.core = (cls.source / CORE).read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def test_patch_scope_and_postimage_are_exact(self) -> None:
        parsed = subprocess.run(
            ["git", "apply", "--numstat", str(PATCH)],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(parsed.stdout, "12\t0\tdrivers/mmc/host/dw_mmc.c\n")
        targets = re.findall(r"^diff --git a/(\S+) b/(\S+)$", self.patch, re.M)
        self.assertEqual(targets, [(str(DRIVER), str(DRIVER))])
        index = re.search(r"^index [0-9a-f]+\.\.([0-9a-f]+) 100644$", self.patch, re.M)
        self.assertIsNotNone(index)
        self.assertEqual(index.group(1), git_blob_oid(self.after)[:12])
        self.assertNotEqual(self.before, self.after)

    def test_command_errors_record_request_and_raw_status(self) -> None:
        body = function_body(self.driver, "static int dw_mci_command_complete")
        marker = "R46H_MMC_CMD_ERROR"
        self.assertEqual(body.count(marker), 1)
        for literal in (
            "if (cmd->error)",
            "mmc_hostname(host->slot->mmc)",
            "cmd->opcode",
            "cmd->arg",
            "status, cmd->error",
        ):
            self.assertIn(literal, body)
        self.assertLess(body.index("if (cmd->error)"), body.index("return cmd->error"))

    def test_data_errors_record_request_and_status(self) -> None:
        body = function_body(self.driver, "static int dw_mci_data_complete")
        marker = "R46H_MMC_DATA_ERROR"
        self.assertEqual(body.count(marker), 1)
        for literal in (
            "if (status & DW_MCI_DATA_ERROR_FLAGS)",
            "data->mrq->cmd->opcode",
            "data->mrq->cmd->arg",
            "status, data->error",
        ):
            self.assertIn(literal, body)
        self.assertLess(body.index(marker), body.index("dw_mci_reset(host)"))
        self.assertIn("mrq->data->mrq = mrq;", self.core)

    def test_added_code_does_not_change_mmc_policy_or_timing(self) -> None:
        added = "\n".join(
            line[1:]
            for line in self.patch.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        self.assertEqual(added.count("dev_err("), 2)
        for forbidden in (
            "mci_writel(",
            "mmc_set_clock",
            "mmc_set_signal_voltage",
            "mmc_power_",
            "host->bus_hz",
            "usleep",
            "msleep",
            "udelay",
            "cmd->retries",
        ):
            self.assertNotIn(forbidden, added)

    def test_candidate_identity_is_exact_and_unique(self) -> None:
        localversion = f"-r46h-mainline-{BUILD_ID}"
        self.assertEqual(
            re.findall(r"^KERNEL_LOCALVERSION=(.+)$", self.manifest, re.M),
            [localversion],
        )
        self.assertEqual(
            re.findall(r'^CONFIG_LOCALVERSION="(.+)"$', self.config, re.M),
            [localversion],
        )
        self.assertEqual(
            re.findall(r'^BUILD_ID="(.+)"$', self.build, re.M), [BUILD_ID]
        )
        self.assertEqual(self.build.count(f"默认 {BUILD_ID}"), 1)
        self.assertEqual(
            re.findall(r"^KERNEL_PATCH_LAST=(.+)$", self.manifest, re.M),
            ["0008"],
        )
        self.assertIn(
            '[[ "$selected_patch_last" == "$KERNEL_PATCH_LAST" ]]',
            self.container_build,
        )

    def test_runbook_preserves_one_shot_and_evidence_boundaries(self) -> None:
        normalized = re.sub(r"\s+", " ", self.runbook)
        for literal in (
            "HOST BUILD PASS",
            "PHYSICAL SAMPLE COMPLETE",
            "fd3a7dbcbad46ce9c437b2244f95cbec22f1f314",
            "init=/bin/bash",
            "rootwait ro rootflags=noload",
            "never use `saveenv`",
            "active p1 remains unchanged",
            "inconclusive diagnostic sample",
            "CMD19",
            "TARGET CLEAN",
            "1500000",
            "I/TC: OP-TEE version",
            "115200",
        ):
            self.assertIn(literal, normalized)


if __name__ == "__main__":
    unittest.main()
