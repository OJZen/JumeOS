#!/usr/bin/env python3
"""Build the host-only full-FBNeo R46H gaming p2 v0.10 successor."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import shutil
import sys


REPO = Path(__file__).resolve().parents[2]
V09_BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v09.py"
V09_BUILDER_PATH = REPO / V09_BUILDER_RELATIVE
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v09_base", V09_BUILDER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the Debian gaming v0.9 builder")
V09 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = V09
SPEC.loader.exec_module(V09)
BASE = V09.BASE


README_RELATIVE = "mainline/rootfs-debian13-gaming-v10/README.md"
PRODUCT_DOC_RELATIVE = "mainline/rootfs-debian13-gaming-v10/PRODUCT.md"
IMAGE_TOOL_RELATIVE = "mainline/rootfs-debian13-gaming-v10/image-in-container.sh"
PAIR_TOOL_RELATIVE = "mainline/rootfs-debian13-gaming-v10/pair-remote-key.sh"
BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v10.py"
TEST_RELATIVE = "mainline/tests/test-debian13-gaming-rootfs-v10.py"

EXTRA_INPUTS = (
    (
        "r46h-firstboot.v09",
        REPO / "mainline/out/r46h-gaming-fbneo-full-v0.1/v09-inputs/r46h-firstboot.v09",
        835,
        "bfe4ee968d3daaa4da040024fbe2d947fc1fd6ff33df66faca0e9628c928d2be",
    ),
    (
        "r46h-rootfs-smoke.v09",
        REPO / "mainline/out/r46h-gaming-fbneo-full-v0.1/v09-inputs/r46h-rootfs-smoke.v09",
        8_294,
        "7b424a024eef28b5e8104384a600ad1b572a71e1da1e0cf0d7a40f6018eb2152",
    ),
)

BASE.CACHE_ROOT = BASE.OUTPUT_ROOT / ".cache/r46h-debian13-gaming-rootfs-v10"
BASE.OUTPUT_NAME = "r46h-debian13-p2-gaming-v0.10"
BASE.ARTIFACT_ID = "debian13-p2-gaming-v0.10"
BASE.IMAGE_NAME = f"{BASE.OUTPUT_NAME}.ext4"
BASE.OUTPUT_DIR = BASE.OUTPUT_ROOT / BASE.OUTPUT_NAME
BASE.BASE_FS_UUID = "d3130009-46a4-4d56-9001-000000000009"
BASE.BASE_FS_LABEL = "R46H_GAMING_V09"
BASE.FS_UUID = "d3130010-46a4-4d56-9001-000000000010"
BASE.FS_LABEL = "R46H_GAMING_V10"
BASE.SOURCE_DATE_EPOCH = "1788480000"
BASE.BASE_IMAGE = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.9/r46h-debian13-p2-gaming-v0.9.ext4"
BASE.BASE_IMAGE_SHA256 = "9b5bf248c39121ad2cfde2d719648469442e9c89f194cfcfca3674336b2e0ea5"
BASE.BASE_BUILD_INFO = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.9/BUILD-INFO"
BASE.BASE_BUILD_INFO_SHA256 = "8062fbe076cfb4cf1b7cace9f5586fe69d79867706579842636649e182473285"
BASE.BASE_CONSOLIDATED_RECEIPT_SHA256 = "b5e8747762aa10c417aee85f18317c4cfaa2103f07a9ba5b33a2873d668db43b"
BASE.BASE_GAMING_RECEIPT_SHA256 = "82721e16a9b9a7c7927d0ca4d228dd3d850e3a39dca245177ec1f016b3b8d314"
BASE.BASE_FIRSTBOOT_SHA256 = EXTRA_INPUTS[0][3]
BASE.FINAL_FIRSTBOOT_SHA256 = "870a23f38abb5b48fdeb65382a9382ae62ad85a0ee08cd95c85303ded706070b"
BASE.BASE_ROOTFS_SMOKE_SHA256 = EXTRA_INPUTS[1][3]
BASE.FINAL_ROOTFS_SMOKE_SHA256 = "b295861ae5d63e9e3fcf1a6c6a8c3f704403af653e8248c84f6ffc02be999bfb"
BASE.VERSION_TEXT = "v0.10"
BASE.VERSION_TOKEN = "V10"
BASE.IMAGE_TOOL_RELATIVE = IMAGE_TOOL_RELATIVE
BASE.BASE_IMAGE_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.9.ext4"
BASE.BASE_BUILD_INFO_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.9.BUILD-INFO"
BASE.DEBUGFS_EVIDENCE_NAME = "DEBUGFS-V10.txt"
BASE.INDEPENDENT_DEBUGFS_EVIDENCE_NAME = "INDEPENDENT-DEBUGFS-V10.txt"
BASE.ARTIFACT_STATUS = "host-only-no-media-operation-performed"

BASE.EXTRA_BUILD_ENVIRONMENT = {
    "BASE_ES_DE_RECEIPT_SHA256": "f459709e392992b6a14caec364edbeeee84ab80f34cafab9a01045e5e837f206",
    "BASE_ES_DE_RUNNER_SHA256": "2c9068d692256f8453cb4f601cd7c5a553b339f0e84b6c269f7f7633020e68f1",
    "BASE_ES_DE_SYSTEMS_SHA256": "bc0929d86b717b8acea82d5be25e12f5c4b01ea9eca6c5981f45ce430492d5a4",
    "BASE_SCREENSHOT_SHA256": "9c4cae9f7a06c88c3b75f8da05049e5f7c22d6f307f8a1250aa7aa3d06b613df",
    "BASE_SYSTEM_LINKS_SHA256": "4fb5406514279bd3ee467f26cbd60379f0b05fc8f8ffc733aa171ec691b7b85e",
    "ES_DE_RECEIPT_SHA256": "c9e26c89fd4f5dd9681b05ad46f27eea1773910a3b207b50be087dfd843866c5",
    "ES_DE_RUNNER_SHA256": "38f0b7f90e417c11a06d70efc70b69cdd5f6409a66a06c1bf8aef69dbd8570f4",
    "ES_DE_SYSTEMS_SHA256": "541e49eca815d55b943a89cd993d81700be4489a5353def501d4e3ea1ed3c243",
    "FBNEO_FULL_CORE_SHA256": "d63bc891a85599949b99748aa5dcd79aed86c29dc859739a9bfe4e1361c02956",
    "GAMING_PAYLOAD_ID": BASE.GAMING_PAYLOAD_ID,
    "SCREENSHOT_SHA256": "8070b9f03f22b7cb4553c8fd56b0dda5f0b42c0f2ae68708fcfa69ae2af525f6",
    "SYSTEM_LINKS_SHA256": "fd01bcf3b0c1bd871539ea54599a77dfd2e861fa221dace69aabb83609b7df66",
}
BASE.EXTRA_BUILD_INFO = {
    "arcade_host_load_samples": "11",
    "consolidated_frontend": "ES-DE-3.4.1-r51",
    "consolidated_remote_input_actions": "16",
    "consolidated_system_count": "9",
    "cps1_host_load_samples": "48",
    "fbneo_full_core_sha256": BASE.EXTRA_BUILD_ENVIRONMENT["FBNEO_FULL_CORE_SHA256"],
    "product_input_count": str(len(EXTRA_INPUTS)),
    "remote_pairing": "required-after-image-write",
    **{
        f"product_input_{name.replace('-', '_').replace('.', '_')}_sha256": digest
        for name, _path, _size, digest in EXTRA_INPUTS
    },
    **{
        f"product_input_{name.replace('-', '_').replace('.', '_')}_size": str(size)
        for name, _path, size, _digest in EXTRA_INPUTS
    },
}
BASE.CONSOLIDATED_RECEIPT_EXTRA_MARKERS = (
    "successor_base_artifact_id=debian13-p2-gaming-v0.9",
    "consolidated_frontend=ES-DE-3.4.1-r51",
    "consolidated_system_count=9",
    "consolidated_remote_input_actions=16",
    "arcade_host_load_samples=11",
    "cps1_host_load_samples=48",
    f"es_de_systems_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['ES_DE_SYSTEMS_SHA256']}",
    f"es_de_system_links_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['SYSTEM_LINKS_SHA256']}",
    f"fbneo_full_core_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['FBNEO_FULL_CORE_SHA256']}",
    "remote_pairing=required-after-image-write",
)
BASE.SOURCE_PATHS = (
    README_RELATIVE,
    PRODUCT_DOC_RELATIVE,
    IMAGE_TOOL_RELATIVE,
    PAIR_TOOL_RELATIVE,
    BUILDER_RELATIVE,
    TEST_RELATIVE,
    V09_BUILDER_RELATIVE,
    V09.V08_BUILDER_RELATIVE,
    V09.V08.BASE_BUILDER_RELATIVE,
    "mainline/deploy/profiles/hl-r46h-v22-g92-v1.json",
    "mainline/gaming-es-de/es_systems.xml",
    "mainline/gaming-es-de/system-links.tsv",
    "mainline/gaming-es-de/r46h-es-de-ui",
    "mainline/gaming-remote-screen/r46h-screenshot",
    "mainline/gaming-fbneo-full/README.md",
    "mainline/gaming-fbneo-full/content-audit.json",
    "mainline/gaming-fbneo-full/source-lock.json",
    "mainline/gaming-fbneo-full/es-system.arcade.xml",
    "mainline/gaming-fbneo-full/es-system.cps1.xml",
    "mainline/gaming-fbneo-full/system-link.arcade.tsv",
    "mainline/gaming-fbneo-full/system-link.cps1.tsv",
)
BASE.APPLY_EVIDENCE = {
    "APPLY-DEBUGFS.txt",
    "CONSOLIDATED-RECEIPT",
    BASE.DEBUGFS_EVIDENCE_NAME,
    "DUMPE2FS.txt",
    "E2FSCK-REPAIR.txt",
    "E2FSCK.txt",
    "EXT4-VERIFIED.sha256",
    "GAMING-PAYLOAD-VERIFY.txt",
    "GAMING-RECEIPT",
    "NORMALIZE-SUPER.txt",
    "PRODUCT-VERIFY.txt",
    "SYSTEMD-VERIFY.txt",
    "TUNE2FS.txt",
    "UDEV-VERIFY.txt",
}
BASE.INDEPENDENT_EVIDENCE = {
    BASE.DEBUGFS_EVIDENCE_NAME: BASE.INDEPENDENT_DEBUGFS_EVIDENCE_NAME,
    "E2FSCK.txt": "INDEPENDENT-E2FSCK.txt",
    "EXT4-VERIFIED.sha256": "INDEPENDENT-EXT4-VERIFIED.sha256",
    "PRODUCT-VERIFY.txt": "INDEPENDENT-PRODUCT-VERIFY.txt",
    "SYSTEMD-VERIFY.txt": "INDEPENDENT-SYSTEMD-VERIFY.txt",
    "UDEV-VERIFY.txt": "INDEPENDENT-UDEV-VERIFY.txt",
}
BASE.REQUIRED_STAGE_FILES = (
    BASE.APPLY_EVIDENCE
    | set(BASE.INDEPENDENT_EVIDENCE.values())
    | {
        "BUILD-COMPLETE",
        "BUILD-INFO",
        "CONTAINER-APPLY.txt",
        "INDEPENDENT-VERIFY.txt",
        "INPUT-ARTIFACTS.sha256",
        "PRODUCT-INPUTS.sha256",
        "REPRODUCE.txt",
        "SHA256SUMS",
        "SOURCE-MANIFEST.json",
        BASE.IMAGE_NAME,
    }
)
BASE.STAGE_RE = re.compile(r"^\.r46h-debian13-p2-gaming-v0\.10\.tmp\.[A-Za-z0-9_]+$")

_validate_inputs = V09._validate_inputs
_write_build_metadata = V09._write_build_metadata
_validate_stage = V09._validate_stage


def validate_inputs(docker: str, extraction_root: Path) -> Path:
    payload = _validate_inputs(docker, extraction_root)
    destination = payload / "product-inputs"
    destination.mkdir(mode=0o700)
    for name, path, size, digest in EXTRA_INPUTS:
        metadata = BASE.require_regular(path, f"v0.10 product input {name}")
        if metadata.st_size != size or BASE.sha256_file(path) != digest:
            raise BASE.BuildError(f"v0.10 product input mismatch: {name}")
        shutil.copyfile(path, destination / name)
    return payload


def product_input_receipt() -> bytes:
    return "".join(
        f"{digest}  {name}\n" for name, _path, _size, digest in EXTRA_INPUTS
    ).encode()


def write_build_metadata(*args: object, **kwargs: object) -> None:
    _write_build_metadata(*args, **kwargs)
    stage = args[0]
    assert isinstance(stage, Path)
    BASE.write_new(stage / "PRODUCT-INPUTS.sha256", product_input_receipt())


def validate_stage(stage: Path, expected_source_commit: str | None = None) -> str:
    image_sha256 = _validate_stage(stage, expected_source_commit)
    if (stage / "PRODUCT-INPUTS.sha256").read_bytes() != product_input_receipt():
        raise BASE.BuildError("v0.10 product input receipt mismatch")
    for name in ("PRODUCT-VERIFY.txt", "INDEPENDENT-PRODUCT-VERIFY.txt"):
        if "R46H_V10_PRODUCT_VERIFY_RESULT=pass" not in (
            stage / name
        ).read_text(encoding="utf-8", errors="replace"):
            raise BASE.BuildError(f"v0.10 product verification marker missing: {name}")
    return image_sha256


BASE.validate_inputs = validate_inputs
BASE.write_build_metadata = write_build_metadata
BASE.validate_stage = validate_stage


if __name__ == "__main__":
    raise SystemExit(BASE.main())
