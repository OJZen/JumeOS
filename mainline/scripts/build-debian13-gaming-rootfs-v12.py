#!/usr/bin/env python3
"""Build the host-only filtered-CPS R46H gaming p2 v0.12 successor."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import shutil
import sys


REPO = Path(__file__).resolve().parents[2]
V11_BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v11.py"
V11_BUILDER_PATH = REPO / V11_BUILDER_RELATIVE
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v11_base", V11_BUILDER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the Debian gaming v0.11 builder")
V11 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = V11
SPEC.loader.exec_module(V11)
BASE = V11.BASE


README_RELATIVE = "mainline/rootfs-debian13-gaming-v12/README.md"
PRODUCT_DOC_RELATIVE = "mainline/rootfs-debian13-gaming-v12/PRODUCT.md"
IMAGE_TOOL_RELATIVE = "mainline/rootfs-debian13-gaming-v12/image-in-container.sh"
BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v12.py"
TEST_RELATIVE = "mainline/tests/test-debian13-gaming-rootfs-v12.py"

EXTRA_INPUTS = (
    (
        "legacy-media-links.tsv",
        REPO / "mainline/out/r46h-gaming-es-de-media-v0.2/legacy-media-links.tsv",
        447_780,
        "b7f647f5903c72e4a3e02dbd993a6c14c07988a983b95dde1c36c524488ad0da",
    ),
    (
        "gamelist.cps2.xml",
        REPO / "mainline/out/r46h-gaming-fbneo-filter-v0.1/gamelist.cps2.xml",
        15_702,
        "a9d78da1e7e780e4a7f73ecd302b79efd381b15fc1a05d23f824ccd27a3daed8",
    ),
    (
        "gamelist.cps3.xml",
        REPO / "mainline/out/r46h-gaming-fbneo-filter-v0.1/gamelist.cps3.xml",
        3_563,
        "9b7bad4b8f955a56cdf405c087222772824358f6a83d58f572fd36152830d45e",
    ),
    (
        "es_settings.v11.xml",
        REPO
        / "mainline/out/r46h-gaming-fbneo-filter-v0.1/v11-inputs/es_settings.v11.xml",
        1_199,
        "2946f7cde318ba23ca5bb3f07bee09dcef8892b254ef621e49c74bb4b60c69c1",
    ),
    (
        "r46h-firstboot.v11",
        REPO
        / "mainline/out/r46h-gaming-fbneo-filter-v0.1/v11-inputs/r46h-firstboot.v11",
        837,
        "cd9ea739b3a84f03392fd33b829aea256b3563827ac87d8447498639c58303f7",
    ),
    (
        "r46h-rootfs-smoke.v11",
        REPO
        / "mainline/out/r46h-gaming-fbneo-filter-v0.1/v11-inputs/r46h-rootfs-smoke.v11",
        8_295,
        "1dc33bd8bea7d8bdbfd8dc471ff740acfacfbcf54e52c7a0e9dd3623641ff046",
    ),
)

BASE.CACHE_ROOT = BASE.OUTPUT_ROOT / ".cache/r46h-debian13-gaming-rootfs-v12"
BASE.OUTPUT_NAME = "r46h-debian13-p2-gaming-v0.12"
BASE.ARTIFACT_ID = "debian13-p2-gaming-v0.12"
BASE.IMAGE_NAME = f"{BASE.OUTPUT_NAME}.ext4"
BASE.OUTPUT_DIR = BASE.OUTPUT_ROOT / BASE.OUTPUT_NAME
BASE.BASE_FS_UUID = "d3130011-46a4-4d56-9001-000000000011"
BASE.BASE_FS_LABEL = "R46H_GAMING_V11"
BASE.FS_UUID = "d3130012-46a4-4d56-9001-000000000012"
BASE.FS_LABEL = "R46H_GAMING_V12"
BASE.SOURCE_DATE_EPOCH = "1788480000"
BASE.BASE_IMAGE = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.11/r46h-debian13-p2-gaming-v0.11.ext4"
BASE.BASE_IMAGE_SHA256 = "d84788c682c1f9e8c13c7fdcc1f0ebea25944aa2933b3633dde18a031b2aac60"
BASE.BASE_BUILD_INFO = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.11/BUILD-INFO"
BASE.BASE_BUILD_INFO_SHA256 = "f8a462c987a5cbcac2d1ae4c054c7844c55d74ea3889f3dd44d58dac8be2a3ab"
BASE.BASE_CONSOLIDATED_RECEIPT_SHA256 = "413990a7e5b22c89e2e528148628c91567dad446b547274a11de2544272882a2"
BASE.BASE_GAMING_RECEIPT_SHA256 = "82721e16a9b9a7c7927d0ca4d228dd3d850e3a39dca245177ec1f016b3b8d314"
BASE.BASE_FIRSTBOOT_SHA256 = EXTRA_INPUTS[4][3]
BASE.FINAL_FIRSTBOOT_SHA256 = "4e1d45a30ee18c0e4db57dbab833311047065dab6cf05bd70dec5c08b7bcaf28"
BASE.BASE_ROOTFS_SMOKE_SHA256 = EXTRA_INPUTS[5][3]
BASE.FINAL_ROOTFS_SMOKE_SHA256 = "2b46b145fb89366bb11e7c34ef8772c5fc501e4b1f0e3b55e2e81c8b2144b118"
BASE.VERSION_TEXT = "v0.12"
BASE.VERSION_TOKEN = "V12"
BASE.IMAGE_TOOL_RELATIVE = IMAGE_TOOL_RELATIVE
BASE.BASE_IMAGE_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.11.ext4"
BASE.BASE_BUILD_INFO_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.11.BUILD-INFO"
BASE.DEBUGFS_EVIDENCE_NAME = "DEBUGFS-V12.txt"
BASE.INDEPENDENT_DEBUGFS_EVIDENCE_NAME = "INDEPENDENT-DEBUGFS-V12.txt"
BASE.ARTIFACT_STATUS = "host-only-no-media-operation-performed"

BASE.EXTRA_BUILD_ENVIRONMENT = {
    "BASE_ES_DE_RECEIPT_SHA256": "8a879a4d37e1f10d704e2a1e09255e534c4595004d299fd3e25955f8ad8f202a",
    "BASE_ES_DE_RUNNER_SHA256": "85dac66e4a893a50e4ba91afd63336c6dc1e48000f572fa0ac302a687b9b9728",
    "BASE_ES_DE_SYSTEMS_SHA256": "541e49eca815d55b943a89cd993d81700be4489a5353def501d4e3ea1ed3c243",
    "BASE_SCREENSHOT_SHA256": "18b92ae1bd1c77d2454a263e1310e6ad7d071ea1a2a75bf28e1957150f6e7f18",
    "BASE_SETTINGS_SHA256": EXTRA_INPUTS[3][3],
    "BASE_SYSTEM_LINKS_SHA256": "fd01bcf3b0c1bd871539ea54599a77dfd2e861fa221dace69aabb83609b7df66",
    "ES_DE_RECEIPT_SHA256": "5e7c20b86320591717924b27ec38493b5e316c134f39b7da75f3854f5d49c92d",
    "ES_DE_RUNNER_SHA256": "f911b81f9f1a1e9460c3ff334ee865e2218e949f69fa25ee10aca69ee7a62a3d",
    "ES_DE_SYSTEMS_SHA256": "81796e9e77e7164d39ee93a0ccba1b03a0e4039354dad203ef5ee5df560a2873",
    "FBNEO_FULL_CORE_SHA256": "d63bc891a85599949b99748aa5dcd79aed86c29dc859739a9bfe4e1361c02956",
    "FILTERED_CPS2_GAMELIST_SHA256": EXTRA_INPUTS[1][3],
    "FILTERED_CPS3_GAMELIST_SHA256": EXTRA_INPUTS[2][3],
    "GAMING_PAYLOAD_ID": BASE.GAMING_PAYLOAD_ID,
    "MEDIA_LINKS_SHA256": EXTRA_INPUTS[0][3],
    "SCREENSHOT_SHA256": "3496a40c14f8c0072df6db502e221b7cd4dbf015a51dc1fb62c345b0226d2a2a",
    "SETTINGS_SHA256": "7162192575638a0ae46655a15929e6a926dd21334567f837c8ef7d9bba42ad01",
    "SYSTEM_LINKS_SHA256": "c12d7707c48b8a67b984e47de21322a9c1eb214e6771d17e63817aca1da8885b",
}
BASE.EXTRA_BUILD_INFO = {
    "arcade_host_load_samples": "11",
    "consolidated_frontend": "ES-DE-3.4.1-r51",
    "consolidated_media_link_count": "6082",
    "consolidated_media_link_delta": "74",
    "consolidated_media_missing_host_fixture": "2396",
    "consolidated_remote_input_actions": "16",
    "consolidated_system_count": "11",
    "cps1_host_load_samples": "48",
    "cps2_host_load_samples": "57",
    "cps3_host_load_samples": "9",
    "es_de_settings_sha256": BASE.EXTRA_BUILD_ENVIRONMENT["SETTINGS_SHA256"],
    "filtered_cps2_gamelist_sha256": EXTRA_INPUTS[1][3],
    "filtered_cps3_gamelist_sha256": EXTRA_INPUTS[2][3],
    "filtered_cps_failure_count": "8",
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
    "successor_base_artifact_id=debian13-p2-gaming-v0.11",
    "consolidated_frontend=ES-DE-3.4.1-r51",
    "consolidated_media_link_count=6082",
    "consolidated_media_link_delta=74",
    "consolidated_media_missing_host_fixture=2396",
    "consolidated_system_count=11",
    "consolidated_remote_input_actions=16",
    "arcade_host_load_samples=11",
    "cps1_host_load_samples=48",
    "cps2_host_load_samples=57",
    "cps3_host_load_samples=9",
    f"es_de_settings_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['SETTINGS_SHA256']}",
    f"filtered_cps2_gamelist_sha256={EXTRA_INPUTS[1][3]}",
    f"filtered_cps3_gamelist_sha256={EXTRA_INPUTS[2][3]}",
    "filtered_cps_failure_count=8",
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
    V11_BUILDER_RELATIVE,
    V11.V10_BUILDER_RELATIVE,
    V11.V10.V09_BUILDER_RELATIVE,
    V11.V10.V09.V08_BUILDER_RELATIVE,
    V11.V10.V09.V08.BASE_BUILDER_RELATIVE,
    "mainline/deploy/profiles/hl-r46h-v22-g92-v1.json",
    "mainline/gaming-es-de/es_systems.xml",
    "mainline/gaming-es-de/system-links.tsv",
    "mainline/gaming-es-de/r46h-es-de-ui",
    "mainline/gaming-es-de/generate-legacy-media-links.py",
    "mainline/gaming-remote-screen/r46h-screenshot",
    "mainline/gaming-fbneo-full/README.md",
    "mainline/gaming-fbneo-full/content-audit.json",
    "mainline/gaming-fbneo-full/es-system.arcade.xml",
    "mainline/gaming-fbneo-full/es-system.cps1.xml",
    "mainline/gaming-fbneo-full/es-systems.cps23.xml",
    "mainline/gaming-fbneo-full/generate-filtered-gamelists.py",
    "mainline/gaming-fbneo-full/system-link.arcade.tsv",
    "mainline/gaming-fbneo-full/system-link.cps1.tsv",
    "mainline/gaming-fbneo-full/system-links.cps23.tsv",
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
BASE.STAGE_RE = re.compile(r"^\.r46h-debian13-p2-gaming-v0\.12\.tmp\.[A-Za-z0-9_]+$")

_validate_inputs = V11._validate_inputs
_write_build_metadata = V11._write_build_metadata
_validate_stage = V11._validate_stage


def validate_inputs(docker: str, extraction_root: Path) -> Path:
    payload = _validate_inputs(docker, extraction_root)
    destination = payload / "product-inputs"
    destination.mkdir(mode=0o700)
    for name, path, size, digest in EXTRA_INPUTS:
        metadata = BASE.require_regular(path, f"v0.12 product input {name}")
        if metadata.st_size != size or BASE.sha256_file(path) != digest:
            raise BASE.BuildError(f"v0.12 product input mismatch: {name}")
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
        raise BASE.BuildError("v0.12 product input receipt mismatch")
    for name in ("MEDIA-VERIFY.txt", "INDEPENDENT-MEDIA-VERIFY.txt"):
        if "R46H_V12_MEDIA_VERIFY_RESULT=pass" not in (
            stage / name
        ).read_text(encoding="utf-8", errors="replace"):
            raise BASE.BuildError(f"v0.12 media verification marker missing: {name}")
    for name in ("PRODUCT-VERIFY.txt", "INDEPENDENT-PRODUCT-VERIFY.txt"):
        if "R46H_V12_PRODUCT_VERIFY_RESULT=pass" not in (
            stage / name
        ).read_text(encoding="utf-8", errors="replace"):
            raise BASE.BuildError(f"v0.12 product verification marker missing: {name}")
    return image_sha256


BASE.validate_inputs = validate_inputs
BASE.write_build_metadata = write_build_metadata
BASE.validate_stage = validate_stage


if __name__ == "__main__":
    raise SystemExit(BASE.main())
