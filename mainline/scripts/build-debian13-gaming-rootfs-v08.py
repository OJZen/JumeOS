#!/usr/bin/env python3
"""Build the host-only consolidated R46H gaming p2 v0.8 successor."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import shutil
import sys


REPO = Path(__file__).resolve().parents[2]
BASE_BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v06.py"
BASE_BUILDER_PATH = REPO / BASE_BUILDER_RELATIVE
SPEC = importlib.util.spec_from_file_location(
    "debian13_gaming_rootfs_consolidated_base", BASE_BUILDER_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the Debian gaming successor builder")
BASE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BASE
SPEC.loader.exec_module(BASE)


README_RELATIVE = "mainline/rootfs-debian13-gaming-v08/README.md"
PRODUCT_DOC_RELATIVE = "mainline/rootfs-debian13-gaming-v08/PRODUCT.md"
IMAGE_TOOL_RELATIVE = "mainline/rootfs-debian13-gaming-v08/image-in-container.sh"
PAIR_TOOL_RELATIVE = "mainline/rootfs-debian13-gaming-v08/pair-remote-key.sh"
BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v08.py"
TEST_RELATIVE = "mainline/tests/test-debian13-gaming-rootfs-v08.py"

EXTRA_INPUTS = (
    (
        "es-de-runtime-v3.4.1.tar.gz",
        REPO / "mainline/out/r46h-gaming-es-de-v0.1/r46h-es-de-runtime-v3.4.1.tar.gz",
        81_738_580,
        "d5de91eb79fa229336d3f0f9c5e0e0d34b0096950cc67928914603209003aa70",
    ),
    (
        "legacy-media-links.tsv",
        REPO / "mainline/out/r46h-gaming-es-de-v0.1/legacy-media-links.tsv",
        269_434,
        "9358e316d0b5436108c4a460a6654c5437341e4c85b86dcc2d5ae32abfbb9a9f",
    ),
    (
        "fbneo-neogeo-libretro.so",
        REPO / "mainline/out/r46h-gaming-ozone-fbneo-v0.1/fbneo_neogeo_libretro.so",
        9_007_520,
        "8bb17a551f3eeeb384ab00a5c5375d30eb63807afe5b6c1ba1d3f78220732bdb",
    ),
    (
        "r46h-drm-capture",
        REPO / "mainline/out/r46h-gaming-remote-screen-v0.2/r46h-drm-capture",
        67_400,
        "77f22181289edd701001fd6570a49afbfde277417e3769a693d1dd335cad324e",
    ),
    (
        "r46h-remote-input",
        REPO / "mainline/out/r46h-gaming-remote-input-v0.1/r46h-remote-input",
        67_480,
        "9907972995127792b75f0cf9922c3d750e8a06437b3d4d026f4a1db614f0232c",
    ),
)

BASE.CACHE_ROOT = BASE.OUTPUT_ROOT / ".cache/r46h-debian13-gaming-rootfs-v08"
BASE.OUTPUT_NAME = "r46h-debian13-p2-gaming-v0.8"
BASE.ARTIFACT_ID = "debian13-p2-gaming-v0.8"
BASE.IMAGE_NAME = f"{BASE.OUTPUT_NAME}.ext4"
BASE.OUTPUT_DIR = BASE.OUTPUT_ROOT / BASE.OUTPUT_NAME

BASE.BASE_FS_UUID = "d3130007-46a4-4d56-9001-000000000007"
BASE.BASE_FS_LABEL = "R46H_GAMING_V07"
BASE.FS_UUID = "d3130008-46a4-4d56-9001-000000000008"
BASE.FS_LABEL = "R46H_GAMING_V08"
BASE.SOURCE_DATE_EPOCH = "1788480000"
BASE.BASE_IMAGE = (
    BASE.OUTPUT_ROOT
    / "r46h-debian13-p2-gaming-v0.7"
    / "r46h-debian13-p2-gaming-v0.7.ext4"
)
BASE.BASE_IMAGE_SHA256 = (
    "17530b491eaf7edd60cb0b499cc0c920af7399673bf9296f30c5753bc1ca7180"
)
BASE.BASE_BUILD_INFO = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.7/BUILD-INFO"
BASE.BASE_BUILD_INFO_SHA256 = (
    "22490e9bafcc0920a382f38d35e193ea033454de4af0a3e1dcda1eb28a84e7a7"
)
BASE.BASE_CONSOLIDATED_RECEIPT_SHA256 = (
    "52152786eb264fcdad7d4a15232494fa393544578e724e598e029862fae9f998"
)
BASE.BASE_GAMING_RECEIPT_SHA256 = (
    "82721e16a9b9a7c7927d0ca4d228dd3d850e3a39dca245177ec1f016b3b8d314"
)

BASE.GAMING_PAYLOAD_ID = "r46h-gaming-mvp-v0.6"
BASE.GAMING_ARCHIVE_NAME = f"{BASE.GAMING_PAYLOAD_ID}.tar.gz"
BASE.GAMING_ARCHIVE = (
    BASE.OUTPUT_ROOT
    / "r46h-gaming-mvp-v0.6/builds/build-73cd84e30548-4c03d9d621ac"
    / BASE.GAMING_ARCHIVE_NAME
)
BASE.GAMING_ARCHIVE_SIZE = 263_537_654
BASE.GAMING_ARCHIVE_SHA256 = (
    "4c03d9d621ac362ce1fdc80628510d1f36e57e7d368eaa600b2f18af44bb31fa"
)
BASE.GAMING_SOURCE_COMMIT = "73cd84e30548d810f32c58dc21a7b2a8ef2a66cc"
BASE.GAMING_PACKAGE_MANIFEST_SHA256 = (
    "c726b6cad27da02ab4f6215b35654319a143858b6bf6e1b641d7b720775ab8f7"
)
BASE.GAMING_PAYLOAD_SHA256SUMS_SHA256 = (
    "d1d9a713b0b70e7bb7834c90a12147039280c72fa00360562eaf754c20035619"
)

BASE.BASE_FIRSTBOOT_SHA256 = (
    "3e4ea0389887c508e4bbcdbae2e07c19018d2777c55256bbbfa596255ffda72d"
)
BASE.FINAL_FIRSTBOOT_SHA256 = (
    "247fbc3d4323e7d072be5802bc84f84a4323944c909f9750ca52dc5367b91643"
)
BASE.BASE_ROOTFS_SMOKE_SHA256 = (
    "b5d04865dcff63c6e8221d7d5ee2261000459f906bbdca2231b98cc1c2bb51cb"
)
BASE.FINAL_ROOTFS_SMOKE_SHA256 = (
    "bde1d2593adf36221a649c861b273ed7ac6bde71f9dc9a06d6b9856934f9ae07"
)

BASE.VERSION_TEXT = "v0.8"
BASE.VERSION_TOKEN = "V08"
BASE.GAMING_PAYLOAD_VERSION_TEXT = "v0.6"
BASE.IMAGE_TOOL_RELATIVE = IMAGE_TOOL_RELATIVE
BASE.BASE_IMAGE_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.7.ext4"
BASE.BASE_BUILD_INFO_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.7.BUILD-INFO"
BASE.DEBUGFS_EVIDENCE_NAME = "DEBUGFS-V08.txt"
BASE.INDEPENDENT_DEBUGFS_EVIDENCE_NAME = "INDEPENDENT-DEBUGFS-V08.txt"
BASE.ARTIFACT_STATUS = "host-only-no-media-operation-performed"

BASE.EXTRA_BUILD_ENVIRONMENT = {
    "BASE_FRONTEND_UNIT_SHA256": "2fec9c8cb0be8ee724c5e9d44d78971ab83e57a4d5cbba9d3931d457262ff9ed",
    "BASE_CONFIG_SHA256": "99a45beb148e58e40983773b4f5e26d9fb5d7e1bbbf6a7e714a5c352e43c0dba",
    "BASE_RUNNER_SHA256": "27d2f987545a3ab20610806923372b41530d41e5e3fc0384614211088d71135c",
    "BASE_VOLUME_HELPER_SHA256": "a66f7ee5fa38dec5964a7d7fa5f72940250952ba3858cbac57626d2f84ff5ec2",
    "BASE_VOLUME_UNIT_SHA256": "f654a838d58d859ee0ccfa75ab87fdab75c5bd465891418bc526d1c61abb8c89",
    "CJK_FONT_SHA256": "acb6440a713d880a13a21b468ba7cd43f5a2b2934972e51be791c880730777b8",
    "CONFIG_SHA256": "0694b9f41220983bdf9d60789b97b2fe115f68474f22f4869a2764513bcf1835",
    "DRM_CAPTURE_SHA256": EXTRA_INPUTS[3][3],
    "ES_DE_BINARY_SHA256": "9c6e50433b9bca5ac1c01030bc4d7b143f05c2cd27c52e6f5f765b0acf01be98",
    "ES_DE_RUNNER_BASE_SHA256": "5b9edd8705d26ac2b58285baee9d2025354a0343936b5360313e664edd5bafa1",
    "ES_DE_RUNNER_SHA256": "a165640c740bab28089794dd24537d9a1949c5fb9f5fc773e8862650400cfe18",
    "ES_DE_RUNTIME_SHA256": EXTRA_INPUTS[0][3],
    "FBNEO_CORE_SHA256": EXTRA_INPUTS[2][3],
    "GAMING_PAYLOAD_ID": BASE.GAMING_PAYLOAD_ID,
    "LEGACY_MEDIA_LINKS_SHA256": EXTRA_INPUTS[1][3],
    "OZONE_RECEIPT_SHA256": "8acac2c8b8e4295c0235ad1fc7e396e341dcc4b1ba771a053355a98cf8fb73ec",
    "REMOTE_GATEWAY_SHA256": "1b1ec52cec6d6e670d49789738d1a6c38d7f1b35c50bb24ba86ff1cd6203f9da",
    "REMOTE_INPUT_SHA256": EXTRA_INPUTS[4][3],
    "REMOTE_SUDOERS_SHA256": "2486b57b1312bea2477c4de629c2b5e60641f9016a3d3fb9c5be70e38b15e1fe",
    "SCREENSHOT_BASE_SHA256": "ce5b38185a92c5043b7ffd4d0a4248d91bc2a189812ed61b2ee68379469d3d04",
    "SCREENSHOT_SHA256": "fe383ed6968aaade131ba33e7646ccfb4922d21c6b76349aaecd350866e3f2d4",
}
BASE.EXTRA_BUILD_INFO = {
    "consolidated_frontend": "ES-DE-3.4.1-r51",
    "consolidated_remote_input_actions": "16",
    "consolidated_system_count": "7",
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
    "successor_base_artifact_id=debian13-p2-gaming-v0.7",
    "consolidated_frontend=ES-DE-3.4.1-r51",
    "consolidated_system_count=7",
    "consolidated_remote_input_actions=16",
    "remote_pairing=required-after-image-write",
    f"es_de_runtime_sha256={EXTRA_INPUTS[0][3]}",
    f"legacy_media_links_sha256={EXTRA_INPUTS[1][3]}",
    f"fbneo_core_sha256={EXTRA_INPUTS[2][3]}",
    f"drm_capture_sha256={EXTRA_INPUTS[3][3]}",
    f"remote_input_sha256={EXTRA_INPUTS[4][3]}",
)

BASE.SOURCE_PATHS = (
    README_RELATIVE,
    PRODUCT_DOC_RELATIVE,
    IMAGE_TOOL_RELATIVE,
    PAIR_TOOL_RELATIVE,
    BUILDER_RELATIVE,
    TEST_RELATIVE,
    BASE_BUILDER_RELATIVE,
    "mainline/deploy/profiles/hl-r46h-v22-g92-v1.json",
    "mainline/gaming-ozone-fbneo/retroarch.cfg",
    "mainline/gaming-ozone-fbneo/r46h-game-ui",
    "mainline/gaming-ozone-fbneo/r46h-volume-keys",
    "mainline/gaming-ozone-fbneo/r46h-volume-keys.service",
    "mainline/gaming-ozone-fbneo/FinalBurn Neo (neogeo subset).opt",
    "mainline/gaming-ozone-fbneo/SNK - Neo Geo.lpl",
    "mainline/gaming-ozone-fbneo/FBNEO-LICENSE.txt",
    "mainline/gaming-es-de/es-de-retroarch.cfg",
    "mainline/gaming-es-de/es_settings.xml",
    "mainline/gaming-es-de/es_systems.xml",
    "mainline/gaming-es-de/r46h-es-de-ui",
    "mainline/gaming-es-de/r46h-gaming-frontend.service",
    "mainline/gaming-es-de/r46h-theme.xml",
    "mainline/gaming-es-de/system-links.tsv",
    "mainline/gaming-remote-screen/r46h-screenshot",
    "mainline/gaming-remote-input/r46h-screenshot-ssh",
    "mainline/gaming-remote-input/r46h-remote-input.sudoers",
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
BASE.STAGE_RE = re.compile(
    r"^\.r46h-debian13-p2-gaming-v0\.8\.tmp\.[A-Za-z0-9]+$"
)

_validate_inputs = BASE.validate_inputs
_write_build_metadata = BASE.write_build_metadata
_validate_stage = BASE.validate_stage


def validate_inputs(docker: str, extraction_root: Path) -> Path:
    payload = _validate_inputs(docker, extraction_root)
    destination = payload / "product-inputs"
    destination.mkdir(mode=0o700)
    for name, path, size, digest in EXTRA_INPUTS:
        metadata = BASE.require_regular(path, f"consolidated product input {name}")
        if metadata.st_size != size or BASE.sha256_file(path) != digest:
            raise BASE.BuildError(f"consolidated product input mismatch: {name}")
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
        raise BASE.BuildError("consolidated product input receipt mismatch")
    for name in ("PRODUCT-VERIFY.txt", "INDEPENDENT-PRODUCT-VERIFY.txt"):
        if "R46H_V08_PRODUCT_VERIFY_RESULT=pass" not in (
            stage / name
        ).read_text(encoding="utf-8", errors="replace"):
            raise BASE.BuildError(f"product verification marker missing: {name}")
    return image_sha256


BASE.validate_inputs = validate_inputs
BASE.write_build_metadata = write_build_metadata
BASE.validate_stage = validate_stage


def main() -> int:
    return BASE.main()


if __name__ == "__main__":
    raise SystemExit(main())
