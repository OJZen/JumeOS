#!/usr/bin/env python3
"""Build the host-only full-FBNeo R46H gaming p2 v0.9 successor."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import shutil
import sys


REPO = Path(__file__).resolve().parents[2]
V08_BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v08.py"
V08_BUILDER_PATH = REPO / V08_BUILDER_RELATIVE
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v08_base", V08_BUILDER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the Debian gaming v0.8 builder")
V08 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = V08
SPEC.loader.exec_module(V08)
BASE = V08.BASE


README_RELATIVE = "mainline/rootfs-debian13-gaming-v09/README.md"
PRODUCT_DOC_RELATIVE = "mainline/rootfs-debian13-gaming-v09/PRODUCT.md"
IMAGE_TOOL_RELATIVE = "mainline/rootfs-debian13-gaming-v09/image-in-container.sh"
PAIR_TOOL_RELATIVE = "mainline/rootfs-debian13-gaming-v09/pair-remote-key.sh"
BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v09.py"
TEST_RELATIVE = "mainline/tests/test-debian13-gaming-rootfs-v09.py"

EXTRA_INPUTS = (
    (
        "fbneo-full-libretro.so",
        REPO / "mainline/out/r46h-gaming-fbneo-full-v0.1/fbneo_libretro.so",
        79_683_320,
        "d63bc891a85599949b99748aa5dcd79aed86c29dc859739a9bfe4e1361c02956",
    ),
    (
        "r46h-firstboot.v08",
        REPO / "mainline/out/r46h-gaming-fbneo-full-v0.1/v08-inputs/r46h-firstboot.v08",
        835,
        "247fbc3d4323e7d072be5802bc84f84a4323944c909f9750ca52dc5367b91643",
    ),
    (
        "r46h-rootfs-smoke.v08",
        REPO / "mainline/out/r46h-gaming-fbneo-full-v0.1/v08-inputs/r46h-rootfs-smoke.v08",
        8_294,
        "bde1d2593adf36221a649c861b273ed7ac6bde71f9dc9a06d6b9856934f9ae07",
    ),
)

BASE.CACHE_ROOT = BASE.OUTPUT_ROOT / ".cache/r46h-debian13-gaming-rootfs-v09"
BASE.OUTPUT_NAME = "r46h-debian13-p2-gaming-v0.9"
BASE.ARTIFACT_ID = "debian13-p2-gaming-v0.9"
BASE.IMAGE_NAME = f"{BASE.OUTPUT_NAME}.ext4"
BASE.OUTPUT_DIR = BASE.OUTPUT_ROOT / BASE.OUTPUT_NAME
BASE.BASE_FS_UUID = "d3130008-46a4-4d56-9001-000000000008"
BASE.BASE_FS_LABEL = "R46H_GAMING_V08"
BASE.FS_UUID = "d3130009-46a4-4d56-9001-000000000009"
BASE.FS_LABEL = "R46H_GAMING_V09"
BASE.SOURCE_DATE_EPOCH = "1788480000"
BASE.BASE_IMAGE = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.8/r46h-debian13-p2-gaming-v0.8.ext4"
BASE.BASE_IMAGE_SHA256 = "da8798c85864fc5ec3abc2cc940cbbbce737090f6281c19d92e301d95bf7247f"
BASE.BASE_BUILD_INFO = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.8/BUILD-INFO"
BASE.BASE_BUILD_INFO_SHA256 = "66d09d48aa26470b5c599e682916057ab5270a6c36fa5ea9577337eb3bef9587"
BASE.BASE_CONSOLIDATED_RECEIPT_SHA256 = "2cf0cf2ee460cc80d578ec4c25e80ccfd16f48c3c7826925d18cf7a513c4c625"
BASE.BASE_GAMING_RECEIPT_SHA256 = "82721e16a9b9a7c7927d0ca4d228dd3d850e3a39dca245177ec1f016b3b8d314"
BASE.BASE_FIRSTBOOT_SHA256 = EXTRA_INPUTS[1][3]
BASE.FINAL_FIRSTBOOT_SHA256 = "bfe4ee968d3daaa4da040024fbe2d947fc1fd6ff33df66faca0e9628c928d2be"
BASE.BASE_ROOTFS_SMOKE_SHA256 = EXTRA_INPUTS[2][3]
BASE.FINAL_ROOTFS_SMOKE_SHA256 = "7b424a024eef28b5e8104384a600ad1b572a71e1da1e0cf0d7a40f6018eb2152"
BASE.VERSION_TEXT = "v0.9"
BASE.VERSION_TOKEN = "V09"
BASE.IMAGE_TOOL_RELATIVE = IMAGE_TOOL_RELATIVE
BASE.BASE_IMAGE_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.8.ext4"
BASE.BASE_BUILD_INFO_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.8.BUILD-INFO"
BASE.DEBUGFS_EVIDENCE_NAME = "DEBUGFS-V09.txt"
BASE.INDEPENDENT_DEBUGFS_EVIDENCE_NAME = "INDEPENDENT-DEBUGFS-V09.txt"
BASE.ARTIFACT_STATUS = "host-only-no-media-operation-performed"

BASE.EXTRA_BUILD_ENVIRONMENT = {
    "BASE_ES_DE_RECEIPT_SHA256": "06cf02afd48b62e763eba83a5828c9df0611c5a893b057a7a2767f21efb40a19",
    "BASE_ES_DE_RUNNER_SHA256": "a165640c740bab28089794dd24537d9a1949c5fb9f5fc773e8862650400cfe18",
    "BASE_ES_DE_SYSTEMS_SHA256": "1f451723d4ce1062157eb0e041ff4c098c5adea98c61e87ddf3cb784dfe630f0",
    "BASE_SCREENSHOT_SHA256": "fe383ed6968aaade131ba33e7646ccfb4922d21c6b76349aaecd350866e3f2d4",
    "BASE_SYSTEM_LINKS_SHA256": "bd5e496ab9bb54f0b9d45b461262b70fd5758d763ea4ff4fb9d06c26c936d73d",
    "ES_DE_RECEIPT_SHA256": "f459709e392992b6a14caec364edbeeee84ab80f34cafab9a01045e5e837f206",
    "ES_DE_RUNNER_SHA256": "2c9068d692256f8453cb4f601cd7c5a553b339f0e84b6c269f7f7633020e68f1",
    "ES_DE_SYSTEMS_SHA256": "bc0929d86b717b8acea82d5be25e12f5c4b01ea9eca6c5981f45ce430492d5a4",
    "FBNEO_FULL_CORE_SHA256": EXTRA_INPUTS[0][3],
    "GAMING_PAYLOAD_ID": BASE.GAMING_PAYLOAD_ID,
    "SCREENSHOT_SHA256": "9c4cae9f7a06c88c3b75f8da05049e5f7c22d6f307f8a1250aa7aa3d06b613df",
    "SYSTEM_LINKS_SHA256": "4fb5406514279bd3ee467f26cbd60379f0b05fc8f8ffc733aa171ec691b7b85e",
}
BASE.EXTRA_BUILD_INFO = {
    "arcade_host_load_samples": "11",
    "consolidated_frontend": "ES-DE-3.4.1-r51",
    "consolidated_remote_input_actions": "16",
    "consolidated_system_count": "8",
    "fbneo_full_core_sha256": EXTRA_INPUTS[0][3],
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
    "successor_base_artifact_id=debian13-p2-gaming-v0.8",
    "consolidated_frontend=ES-DE-3.4.1-r51",
    "consolidated_system_count=8",
    "consolidated_remote_input_actions=16",
    "arcade_host_load_samples=11",
    f"es_de_systems_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['ES_DE_SYSTEMS_SHA256']}",
    f"es_de_system_links_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['SYSTEM_LINKS_SHA256']}",
    f"fbneo_full_core_sha256={EXTRA_INPUTS[0][3]}",
    "remote_pairing=required-after-image-write",
)
BASE.SOURCE_PATHS = (
    README_RELATIVE,
    PRODUCT_DOC_RELATIVE,
    IMAGE_TOOL_RELATIVE,
    PAIR_TOOL_RELATIVE,
    BUILDER_RELATIVE,
    TEST_RELATIVE,
    V08_BUILDER_RELATIVE,
    V08.BASE_BUILDER_RELATIVE,
    "mainline/deploy/profiles/hl-r46h-v22-g92-v1.json",
    "mainline/gaming-es-de/es_systems.xml",
    "mainline/gaming-es-de/system-links.tsv",
    "mainline/gaming-es-de/r46h-es-de-ui",
    "mainline/gaming-remote-screen/r46h-screenshot",
    "mainline/gaming-fbneo-full/README.md",
    "mainline/gaming-fbneo-full/source-lock.json",
    "mainline/gaming-fbneo-full/es-system.arcade.xml",
    "mainline/gaming-fbneo-full/system-link.arcade.tsv",
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
BASE.STAGE_RE = re.compile(r"^\.r46h-debian13-p2-gaming-v0\.9\.tmp\.[A-Za-z0-9_]+$")

_validate_inputs = V08._validate_inputs
_write_build_metadata = V08._write_build_metadata
_validate_stage = V08._validate_stage


def validate_inputs(docker: str, extraction_root: Path) -> Path:
    payload = _validate_inputs(docker, extraction_root)
    destination = payload / "product-inputs"
    destination.mkdir(mode=0o700)
    for name, path, size, digest in EXTRA_INPUTS:
        metadata = BASE.require_regular(path, f"v0.9 product input {name}")
        if metadata.st_size != size or BASE.sha256_file(path) != digest:
            raise BASE.BuildError(f"v0.9 product input mismatch: {name}")
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
        raise BASE.BuildError("v0.9 product input receipt mismatch")
    for name in ("PRODUCT-VERIFY.txt", "INDEPENDENT-PRODUCT-VERIFY.txt"):
        if "R46H_V09_PRODUCT_VERIFY_RESULT=pass" not in (
            stage / name
        ).read_text(encoding="utf-8", errors="replace"):
            raise BASE.BuildError(f"v0.9 product verification marker missing: {name}")
    return image_sha256


BASE.validate_inputs = validate_inputs
BASE.write_build_metadata = write_build_metadata
BASE.validate_stage = validate_stage


if __name__ == "__main__":
    raise SystemExit(BASE.main())
