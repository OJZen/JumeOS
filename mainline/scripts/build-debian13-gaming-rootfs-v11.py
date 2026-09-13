#!/usr/bin/env python3
"""Build the host-only ES-DE media R46H gaming p2 v0.11 successor."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import shutil
import sys


REPO = Path(__file__).resolve().parents[2]
V10_BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v10.py"
V10_BUILDER_PATH = REPO / V10_BUILDER_RELATIVE
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v10_base", V10_BUILDER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the Debian gaming v0.10 builder")
V10 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = V10
SPEC.loader.exec_module(V10)
BASE = V10.BASE


README_RELATIVE = "mainline/rootfs-debian13-gaming-v11/README.md"
PRODUCT_DOC_RELATIVE = "mainline/rootfs-debian13-gaming-v11/PRODUCT.md"
IMAGE_TOOL_RELATIVE = "mainline/rootfs-debian13-gaming-v11/image-in-container.sh"
BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v11.py"
TEST_RELATIVE = "mainline/tests/test-debian13-gaming-rootfs-v11.py"

EXTRA_INPUTS = (
    (
        "legacy-media-links.tsv",
        REPO / "mainline/out/r46h-gaming-es-de-media-v0.1/legacy-media-links.tsv",
        439_914,
        "4903e8bdc5165cbb6bb993dd2632c2e8ec8b2608514c5a5f74e24d9266786cf9",
    ),
    (
        "r46h-firstboot.v10",
        REPO / "mainline/out/r46h-gaming-es-de-media-v0.1/v10-inputs/r46h-firstboot.v10",
        837,
        "870a23f38abb5b48fdeb65382a9382ae62ad85a0ee08cd95c85303ded706070b",
    ),
    (
        "r46h-rootfs-smoke.v10",
        REPO / "mainline/out/r46h-gaming-es-de-media-v0.1/v10-inputs/r46h-rootfs-smoke.v10",
        8_295,
        "b295861ae5d63e9e3fcf1a6c6a8c3f704403af653e8248c84f6ffc02be999bfb",
    ),
)

BASE.CACHE_ROOT = BASE.OUTPUT_ROOT / ".cache/r46h-debian13-gaming-rootfs-v11"
BASE.OUTPUT_NAME = "r46h-debian13-p2-gaming-v0.11"
BASE.ARTIFACT_ID = "debian13-p2-gaming-v0.11"
BASE.IMAGE_NAME = f"{BASE.OUTPUT_NAME}.ext4"
BASE.OUTPUT_DIR = BASE.OUTPUT_ROOT / BASE.OUTPUT_NAME
BASE.BASE_FS_UUID = "d3130010-46a4-4d56-9001-000000000010"
BASE.BASE_FS_LABEL = "R46H_GAMING_V10"
BASE.FS_UUID = "d3130011-46a4-4d56-9001-000000000011"
BASE.FS_LABEL = "R46H_GAMING_V11"
BASE.SOURCE_DATE_EPOCH = "1788480000"
BASE.BASE_IMAGE = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.10/r46h-debian13-p2-gaming-v0.10.ext4"
BASE.BASE_IMAGE_SHA256 = "71f0da96c972dca90dc1c40fff8ec36a46afb3ad0535fff1584a983575d77adf"
BASE.BASE_BUILD_INFO = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.10/BUILD-INFO"
BASE.BASE_BUILD_INFO_SHA256 = "bce3868fc2e20ebfd998952553979b464997a4716c24983e720a9b92491ef92d"
BASE.BASE_CONSOLIDATED_RECEIPT_SHA256 = "9df568ff7cd368e1d6c8d89f84fc715431ec721625d5999e873557cc714056f5"
BASE.BASE_GAMING_RECEIPT_SHA256 = "82721e16a9b9a7c7927d0ca4d228dd3d850e3a39dca245177ec1f016b3b8d314"
BASE.BASE_FIRSTBOOT_SHA256 = EXTRA_INPUTS[1][3]
BASE.FINAL_FIRSTBOOT_SHA256 = "cd9ea739b3a84f03392fd33b829aea256b3563827ac87d8447498639c58303f7"
BASE.BASE_ROOTFS_SMOKE_SHA256 = EXTRA_INPUTS[2][3]
BASE.FINAL_ROOTFS_SMOKE_SHA256 = "1dc33bd8bea7d8bdbfd8dc471ff740acfacfbcf54e52c7a0e9dd3623641ff046"
BASE.VERSION_TEXT = "v0.11"
BASE.VERSION_TOKEN = "V11"
BASE.IMAGE_TOOL_RELATIVE = IMAGE_TOOL_RELATIVE
BASE.BASE_IMAGE_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.10.ext4"
BASE.BASE_BUILD_INFO_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.10.BUILD-INFO"
BASE.DEBUGFS_EVIDENCE_NAME = "DEBUGFS-V11.txt"
BASE.INDEPENDENT_DEBUGFS_EVIDENCE_NAME = "INDEPENDENT-DEBUGFS-V11.txt"
BASE.ARTIFACT_STATUS = "host-only-no-media-operation-performed"

BASE.EXTRA_BUILD_ENVIRONMENT = {
    "BASE_ES_DE_RECEIPT_SHA256": "c9e26c89fd4f5dd9681b05ad46f27eea1773910a3b207b50be087dfd843866c5",
    "BASE_ES_DE_RUNNER_SHA256": "38f0b7f90e417c11a06d70efc70b69cdd5f6409a66a06c1bf8aef69dbd8570f4",
    "BASE_ES_DE_SYSTEMS_SHA256": "541e49eca815d55b943a89cd993d81700be4489a5353def501d4e3ea1ed3c243",
    "BASE_SCREENSHOT_SHA256": "8070b9f03f22b7cb4553c8fd56b0dda5f0b42c0f2ae68708fcfa69ae2af525f6",
    "BASE_SYSTEM_LINKS_SHA256": "fd01bcf3b0c1bd871539ea54599a77dfd2e861fa221dace69aabb83609b7df66",
    "ES_DE_RECEIPT_SHA256": "8a879a4d37e1f10d704e2a1e09255e534c4595004d299fd3e25955f8ad8f202a",
    "ES_DE_RUNNER_SHA256": "85dac66e4a893a50e4ba91afd63336c6dc1e48000f572fa0ac302a687b9b9728",
    "ES_DE_SYSTEMS_SHA256": "541e49eca815d55b943a89cd993d81700be4489a5353def501d4e3ea1ed3c243",
    "FBNEO_FULL_CORE_SHA256": "d63bc891a85599949b99748aa5dcd79aed86c29dc859739a9bfe4e1361c02956",
    "GAMING_PAYLOAD_ID": BASE.GAMING_PAYLOAD_ID,
    "MEDIA_LINKS_SHA256": EXTRA_INPUTS[0][3],
    "SCREENSHOT_SHA256": "18b92ae1bd1c77d2454a263e1310e6ad7d071ea1a2a75bf28e1957150f6e7f18",
    "SYSTEM_LINKS_SHA256": "fd01bcf3b0c1bd871539ea54599a77dfd2e861fa221dace69aabb83609b7df66",
}
BASE.EXTRA_BUILD_INFO = {
    "arcade_host_load_samples": "11",
    "consolidated_frontend": "ES-DE-3.4.1-r51",
    "consolidated_media_link_count": "6008",
    "consolidated_media_link_delta": "2591",
    "consolidated_media_missing_host_fixture": "2322",
    "consolidated_remote_input_actions": "16",
    "consolidated_system_count": "9",
    "cps1_host_load_samples": "48",
    "fbneo_full_core_sha256": BASE.EXTRA_BUILD_ENVIRONMENT["FBNEO_FULL_CORE_SHA256"],
    "legacy_media_links_sha256": EXTRA_INPUTS[0][3],
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
    "successor_base_artifact_id=debian13-p2-gaming-v0.10",
    "consolidated_frontend=ES-DE-3.4.1-r51",
    "consolidated_media_link_count=6008",
    "consolidated_media_link_delta=2591",
    "consolidated_media_missing_host_fixture=2322",
    "consolidated_system_count=9",
    "consolidated_remote_input_actions=16",
    "arcade_host_load_samples=11",
    "cps1_host_load_samples=48",
    f"es_de_systems_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['ES_DE_SYSTEMS_SHA256']}",
    f"es_de_system_links_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['SYSTEM_LINKS_SHA256']}",
    f"fbneo_full_core_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['FBNEO_FULL_CORE_SHA256']}",
    f"legacy_media_links_sha256={EXTRA_INPUTS[0][3]}",
    "remote_pairing=required-after-image-write",
)
BASE.SOURCE_PATHS = (
    README_RELATIVE,
    PRODUCT_DOC_RELATIVE,
    IMAGE_TOOL_RELATIVE,
    BUILDER_RELATIVE,
    TEST_RELATIVE,
    V10_BUILDER_RELATIVE,
    V10.V09_BUILDER_RELATIVE,
    V10.V09.V08_BUILDER_RELATIVE,
    V10.V09.V08.BASE_BUILDER_RELATIVE,
    "mainline/deploy/profiles/hl-r46h-v22-g92-v1.json",
    "mainline/gaming-es-de/es_systems.xml",
    "mainline/gaming-es-de/system-links.tsv",
    "mainline/gaming-es-de/r46h-es-de-ui",
    "mainline/gaming-es-de/generate-legacy-media-links.py",
    "mainline/gaming-remote-screen/r46h-screenshot",
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
    "MEDIA-VERIFY.txt",
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
    "MEDIA-VERIFY.txt": "INDEPENDENT-MEDIA-VERIFY.txt",
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
BASE.STAGE_RE = re.compile(r"^\.r46h-debian13-p2-gaming-v0\.11\.tmp\.[A-Za-z0-9_]+$")

_validate_inputs = V10._validate_inputs
_write_build_metadata = V10._write_build_metadata
_validate_stage = V10._validate_stage


def validate_inputs(docker: str, extraction_root: Path) -> Path:
    payload = _validate_inputs(docker, extraction_root)
    destination = payload / "product-inputs"
    destination.mkdir(mode=0o700)
    for name, path, size, digest in EXTRA_INPUTS:
        metadata = BASE.require_regular(path, f"v0.11 product input {name}")
        if metadata.st_size != size or BASE.sha256_file(path) != digest:
            raise BASE.BuildError(f"v0.11 product input mismatch: {name}")
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
        raise BASE.BuildError("v0.11 product input receipt mismatch")
    for name in ("MEDIA-VERIFY.txt", "INDEPENDENT-MEDIA-VERIFY.txt"):
        if "R46H_V11_MEDIA_VERIFY_RESULT=pass" not in (
            stage / name
        ).read_text(encoding="utf-8", errors="replace"):
            raise BASE.BuildError(f"v0.11 media verification marker missing: {name}")
    for name in ("PRODUCT-VERIFY.txt", "INDEPENDENT-PRODUCT-VERIFY.txt"):
        if "R46H_V11_PRODUCT_VERIFY_RESULT=pass" not in (
            stage / name
        ).read_text(encoding="utf-8", errors="replace"):
            raise BASE.BuildError(f"v0.11 product verification marker missing: {name}")
    return image_sha256


BASE.validate_inputs = validate_inputs
BASE.write_build_metadata = write_build_metadata
BASE.validate_stage = validate_stage


if __name__ == "__main__":
    raise SystemExit(BASE.main())
