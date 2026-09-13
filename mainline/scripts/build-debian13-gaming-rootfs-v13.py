#!/usr/bin/env python3
"""Build the host-only PPSSPP R46H gaming p2 v0.13 successor."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import shutil
import sys


REPO = Path(__file__).resolve().parents[2]
V12_BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v12.py"
V12_BUILDER_PATH = REPO / V12_BUILDER_RELATIVE
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v12_base", V12_BUILDER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the Debian gaming v0.12 builder")
V12 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = V12
SPEC.loader.exec_module(V12)
BASE = V12.BASE


README_RELATIVE = "mainline/rootfs-debian13-gaming-v13/README.md"
PRODUCT_DOC_RELATIVE = "mainline/rootfs-debian13-gaming-v13/PRODUCT.md"
IMAGE_TOOL_RELATIVE = "mainline/rootfs-debian13-gaming-v13/image-in-container.sh"
BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v13.py"
TEST_RELATIVE = "mainline/tests/test-debian13-gaming-rootfs-v13.py"

EXTRA_INPUTS = (
    (
        "r46h-ppsspp-libretro-v1.20.4.tar.gz",
        REPO / "mainline/out/r46h-gaming-ppsspp-v0.1/r46h-ppsspp-libretro-v1.20.4.tar.gz",
        19_260_809,
        "8940315762f7abb91624d009f13cddafdb1ab644e41f8e4bf3be70a5a875bc04",
    ),
    (
        "gamelist.psp.xml",
        REPO / "mainline/out/r46h-gaming-ppsspp-content-v0.1/gamelist.psp.xml",
        1_021,
        "c2f722c494fa623f9b31b7c9a4eab1fa0aca9409262fa82d2631dbc728ed5288",
    ),
    (
        "legacy-media-links.tsv",
        REPO / "mainline/out/r46h-gaming-ppsspp-content-v0.1/legacy-media-links.tsv",
        448_200,
        "5e2e35d671a57c93faefe5715a541b5cda3ffc273458f99e7c35adbb2fa7ecf8",
    ),
    (
        "core-options.v12.cfg",
        REPO / "mainline/out/r46h-gaming-ppsspp-content-v0.1/v12-inputs/core-options.cfg",
        1_725,
        "4e67299bc6c37cd1ebdfca4e6a42110d5071c62d00e714b952b906ca1fa68976",
    ),
    (
        "r46h-firstboot.v12",
        REPO / "mainline/out/r46h-gaming-ppsspp-content-v0.1/v12-inputs/firstboot",
        837,
        "4e1d45a30ee18c0e4db57dbab833311047065dab6cf05bd70dec5c08b7bcaf28",
    ),
    (
        "es-de-retroarch.v12.cfg",
        REPO / "mainline/out/r46h-gaming-ppsspp-content-v0.1/v12-inputs/retroarch-append.cfg",
        375,
        "2e13e4d33ca23e67d7b52ce6c9c85045b39e3f2ff76bbd6d68c8ca2295ddcb7f",
    ),
    (
        "r46h-es-de-ui.v12",
        REPO / "mainline/out/r46h-gaming-ppsspp-content-v0.1/v12-inputs/runner",
        8_571,
        "f911b81f9f1a1e9460c3ff334ee865e2218e949f69fa25ee10aca69ee7a62a3d",
    ),
    (
        "r46h-screenshot.v12",
        REPO / "mainline/out/r46h-gaming-ppsspp-content-v0.1/v12-inputs/screenshot",
        11_281,
        "3496a40c14f8c0072df6db502e221b7cd4dbf015a51dc1fb62c345b0226d2a2a",
    ),
    (
        "r46h-rootfs-smoke.v12",
        REPO / "mainline/out/r46h-gaming-ppsspp-content-v0.1/v12-inputs/smoke",
        8_295,
        "2b46b145fb89366bb11e7c34ef8772c5fc501e4b1f0e3b55e2e81c8b2144b118",
    ),
    (
        "system-links.v12.tsv",
        REPO / "mainline/out/r46h-gaming-ppsspp-content-v0.1/v12-inputs/system-links.tsv",
        231,
        "c12d7707c48b8a67b984e47de21322a9c1eb214e6771d17e63817aca1da8885b",
    ),
    (
        "es-de-systems.v12.xml",
        REPO / "mainline/out/r46h-gaming-ppsspp-content-v0.1/v12-inputs/systems.xml",
        5_522,
        "81796e9e77e7164d39ee93a0ccba1b03a0e4039354dad203ef5ee5df560a2873",
    ),
)

BASE.CACHE_ROOT = BASE.OUTPUT_ROOT / ".cache/r46h-debian13-gaming-rootfs-v13"
BASE.OUTPUT_NAME = "r46h-debian13-p2-gaming-v0.13"
BASE.ARTIFACT_ID = "debian13-p2-gaming-v0.13"
BASE.IMAGE_NAME = f"{BASE.OUTPUT_NAME}.ext4"
BASE.OUTPUT_DIR = BASE.OUTPUT_ROOT / BASE.OUTPUT_NAME
BASE.BASE_FS_UUID = "d3130012-46a4-4d56-9001-000000000012"
BASE.BASE_FS_LABEL = "R46H_GAMING_V12"
BASE.FS_UUID = "d3130013-46a4-4d56-9001-000000000013"
BASE.FS_LABEL = "R46H_GAMING_V13"
BASE.SOURCE_DATE_EPOCH = "1788480000"
BASE.BASE_IMAGE = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.12/r46h-debian13-p2-gaming-v0.12.ext4"
BASE.BASE_IMAGE_SHA256 = "af3235742a0324453a6193bc0c3ec0e149fffcf9f6c0c22dba4e2f2e082a9111"
BASE.BASE_BUILD_INFO = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.12/BUILD-INFO"
BASE.BASE_BUILD_INFO_SHA256 = "dcc7d0e526d9efe0f2bb58930cc008d672091c3b262fd3afa1694bb1a4a7fcf4"
BASE.BASE_CONSOLIDATED_RECEIPT_SHA256 = "8986487122f164235e6744c0afe1497df7ba4693f345c8823bfe2bafe2fab033"
BASE.BASE_GAMING_RECEIPT_SHA256 = "82721e16a9b9a7c7927d0ca4d228dd3d850e3a39dca245177ec1f016b3b8d314"
BASE.BASE_FIRSTBOOT_SHA256 = "4e1d45a30ee18c0e4db57dbab833311047065dab6cf05bd70dec5c08b7bcaf28"
BASE.FINAL_FIRSTBOOT_SHA256 = "fc8b4c37b5b7005babe0990cefd471ef12d60ad122276fd61a2bddbd1b473602"
BASE.BASE_ROOTFS_SMOKE_SHA256 = "2b46b145fb89366bb11e7c34ef8772c5fc501e4b1f0e3b55e2e81c8b2144b118"
BASE.FINAL_ROOTFS_SMOKE_SHA256 = "724da6be841f1d69eba7752287fcb6c3c7dfc66899baa4f3be6a2e5e5492a5f6"
BASE.VERSION_TEXT = "v0.13"
BASE.VERSION_TOKEN = "V13"
BASE.IMAGE_TOOL_RELATIVE = IMAGE_TOOL_RELATIVE
BASE.BASE_IMAGE_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.12.ext4"
BASE.BASE_BUILD_INFO_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.12.BUILD-INFO"
BASE.DEBUGFS_EVIDENCE_NAME = "DEBUGFS-V13.txt"
BASE.INDEPENDENT_DEBUGFS_EVIDENCE_NAME = "INDEPENDENT-DEBUGFS-V13.txt"
BASE.ARTIFACT_STATUS = "host-only-no-media-operation-performed"

BASE.EXTRA_BUILD_ENVIRONMENT = {
    "BASE_CORE_OPTIONS_SHA256": "4e67299bc6c37cd1ebdfca4e6a42110d5071c62d00e714b952b906ca1fa68976",
    "BASE_ES_DE_RECEIPT_SHA256": "5e7c20b86320591717924b27ec38493b5e316c134f39b7da75f3854f5d49c92d",
    "BASE_ES_DE_RUNNER_SHA256": "f911b81f9f1a1e9460c3ff334ee865e2218e949f69fa25ee10aca69ee7a62a3d",
    "BASE_ES_DE_SYSTEMS_SHA256": "81796e9e77e7164d39ee93a0ccba1b03a0e4039354dad203ef5ee5df560a2873",
    "BASE_MEDIA_LINKS_SHA256": "b7f647f5903c72e4a3e02dbd993a6c14c07988a983b95dde1c36c524488ad0da",
    "BASE_RETROARCH_APPEND_SHA256": "2e13e4d33ca23e67d7b52ce6c9c85045b39e3f2ff76bbd6d68c8ca2295ddcb7f",
    "BASE_SCREENSHOT_SHA256": "3496a40c14f8c0072df6db502e221b7cd4dbf015a51dc1fb62c345b0226d2a2a",
    "BASE_SETTINGS_SHA256": "7162192575638a0ae46655a15929e6a926dd21334567f837c8ef7d9bba42ad01",
    "BASE_SYSTEM_LINKS_SHA256": "c12d7707c48b8a67b984e47de21322a9c1eb214e6771d17e63817aca1da8885b",
    "CORE_OPTIONS_SHA256": "d9328c8675c06dc2f9f75c16617c7753357d89e2deb095619e704b3f34763370",
    "ES_DE_RECEIPT_SHA256": "75267ae9b44d4c40b15a3485fd220501cfa10aa005626ebe31709b17c9379099",
    "ES_DE_RUNNER_SHA256": "525147cbe8c5095efee3d64da3245595b2926cfb5584199a9fdaf6d2db3ea54c",
    "ES_DE_SYSTEMS_SHA256": "4578796d0e2b9bb9d27b312640b043a4e1496b0b768405bb45a0f683ea12df92",
    "FBNEO_FULL_CORE_SHA256": "d63bc891a85599949b99748aa5dcd79aed86c29dc859739a9bfe4e1361c02956",
    "FILTERED_PSP_GAMELIST_SHA256": EXTRA_INPUTS[1][3],
    "GAMING_PAYLOAD_ID": BASE.GAMING_PAYLOAD_ID,
    "MEDIA_LINKS_SHA256": EXTRA_INPUTS[2][3],
    "PPSSPP_ASSETS_MANIFEST_SHA256": "98c8b6f16f9fe7f8def8c78a1f2b48b62744ee8b45afa4cf5c65b3c0fce80abb",
    "PPSSPP_BUNDLE_SHA256": EXTRA_INPUTS[0][3],
    "PPSSPP_CORE_SHA256": "f39819580dc5a867bd8674eef37b13c2eef328824b1aabe7ed4dc98af61bf3a7",
    "RETROARCH_APPEND_SHA256": "d9bb66ae213d5ef30da941f238322640103af69252c5a6d2bf4f9838ee756975",
    "SCREENSHOT_SHA256": "7f7eecd0d0743be914473fc4a128d0a95ad50947405282c9c401ed70db4271b4",
    "SYSTEM_LINKS_SHA256": "6d40682a240210e6e88f4a104df9dc32e52414585528e69ab5eba87b632804d8",
}
BASE.EXTRA_BUILD_INFO = {
    "consolidated_frontend": "ES-DE-3.4.1-r51",
    "consolidated_media_link_count": "6087",
    "consolidated_media_link_delta": "5",
    "consolidated_media_missing_host_fixture": "2396",
    "consolidated_remote_input_actions": "16",
    "consolidated_system_count": "12",
    "es_de_core_options_sha256": BASE.EXTRA_BUILD_ENVIRONMENT["CORE_OPTIONS_SHA256"],
    "es_de_settings_sha256": BASE.EXTRA_BUILD_ENVIRONMENT["BASE_SETTINGS_SHA256"],
    "filtered_psp_gamelist_sha256": EXTRA_INPUTS[1][3],
    "legacy_media_links_sha256": EXTRA_INPUTS[2][3],
    "ppsspp_assets_manifest_sha256": BASE.EXTRA_BUILD_ENVIRONMENT["PPSSPP_ASSETS_MANIFEST_SHA256"],
    "ppsspp_bundle_sha256": EXTRA_INPUTS[0][3],
    "ppsspp_core_sha256": BASE.EXTRA_BUILD_ENVIRONMENT["PPSSPP_CORE_SHA256"],
    "ppsspp_host_load_samples": "6",
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
    "successor_base_artifact_id=debian13-p2-gaming-v0.12",
    "consolidated_frontend=ES-DE-3.4.1-r51",
    "consolidated_media_link_count=6087",
    "consolidated_media_link_delta=5",
    "consolidated_media_missing_host_fixture=2396",
    "consolidated_system_count=12",
    "consolidated_remote_input_actions=16",
    "ppsspp_host_load_samples=6",
    f"es_de_core_options_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['CORE_OPTIONS_SHA256']}",
    f"es_de_systems_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['ES_DE_SYSTEMS_SHA256']}",
    f"es_de_system_links_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['SYSTEM_LINKS_SHA256']}",
    f"filtered_psp_gamelist_sha256={EXTRA_INPUTS[1][3]}",
    f"legacy_media_links_sha256={EXTRA_INPUTS[2][3]}",
    f"ppsspp_assets_manifest_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['PPSSPP_ASSETS_MANIFEST_SHA256']}",
    f"ppsspp_bundle_sha256={EXTRA_INPUTS[0][3]}",
    f"ppsspp_core_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['PPSSPP_CORE_SHA256']}",
    "remote_pairing=required-after-image-write",
)
BASE.SOURCE_PATHS = (
    README_RELATIVE,
    PRODUCT_DOC_RELATIVE,
    IMAGE_TOOL_RELATIVE,
    BUILDER_RELATIVE,
    TEST_RELATIVE,
    V12_BUILDER_RELATIVE,
    V12.V11_BUILDER_RELATIVE,
    V12.V11.V10_BUILDER_RELATIVE,
    V12.V11.V10.V09_BUILDER_RELATIVE,
    V12.V11.V10.V09.V08_BUILDER_RELATIVE,
    V12.V11.V10.V09.V08.BASE_BUILDER_RELATIVE,
    "mainline/deploy/profiles/hl-r46h-v22-g92-v1.json",
    "mainline/gaming-ppsspp/README.md",
    "mainline/gaming-ppsspp/build-core.py",
    "mainline/gaming-ppsspp/content-audit.json",
    "mainline/gaming-ppsspp/core-options.cfg",
    "mainline/gaming-ppsspp/es-system.psp.xml",
    "mainline/gaming-ppsspp/generate-filtered-gamelist.py",
    "mainline/gaming-ppsspp/source-lock.json",
    "mainline/gaming-ppsspp/system-link.psp.tsv",
    "mainline/gaming-ppsspp/transform-es-de-runner.awk",
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
    "PPSSPP-VERIFY.txt",
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
    "PPSSPP-VERIFY.txt": "INDEPENDENT-PPSSPP-VERIFY.txt",
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
BASE.STAGE_RE = re.compile(r"^\.r46h-debian13-p2-gaming-v0\.13\.tmp\.[A-Za-z0-9_]+$")

_validate_inputs = V12._validate_inputs
_write_build_metadata = V12._write_build_metadata
_validate_stage = V12._validate_stage


def validate_inputs(docker: str, extraction_root: Path) -> Path:
    payload = _validate_inputs(docker, extraction_root)
    destination = payload / "product-inputs"
    destination.mkdir(mode=0o700)
    for name, path, size, digest in EXTRA_INPUTS:
        metadata = BASE.require_regular(path, f"v0.13 product input {name}")
        if metadata.st_size != size or BASE.sha256_file(path) != digest:
            raise BASE.BuildError(f"v0.13 product input mismatch: {name}")
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
        raise BASE.BuildError("v0.13 product input receipt mismatch")
    for name in ("MEDIA-VERIFY.txt", "INDEPENDENT-MEDIA-VERIFY.txt"):
        if "R46H_V13_MEDIA_VERIFY_RESULT=pass" not in (stage / name).read_text(
            encoding="utf-8", errors="replace"
        ):
            raise BASE.BuildError(f"v0.13 media verification marker missing: {name}")
    for name in ("PPSSPP-VERIFY.txt", "INDEPENDENT-PPSSPP-VERIFY.txt"):
        if "R46H_V13_PPSSPP_VERIFY_RESULT=pass" not in (stage / name).read_text(
            encoding="utf-8", errors="replace"
        ):
            raise BASE.BuildError(f"v0.13 PPSSPP verification marker missing: {name}")
    for name in ("PRODUCT-VERIFY.txt", "INDEPENDENT-PRODUCT-VERIFY.txt"):
        if "R46H_V13_PRODUCT_VERIFY_RESULT=pass" not in (stage / name).read_text(
            encoding="utf-8", errors="replace"
        ):
            raise BASE.BuildError(f"v0.13 product verification marker missing: {name}")
    return image_sha256


BASE.validate_inputs = validate_inputs
BASE.write_build_metadata = write_build_metadata
BASE.validate_stage = validate_stage


if __name__ == "__main__":
    raise SystemExit(BASE.main())
