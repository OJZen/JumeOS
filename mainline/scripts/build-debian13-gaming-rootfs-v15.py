#!/usr/bin/env python3
"""Build the host-only Game Gear R46H gaming p2 v0.15 successor."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import shutil
import sys


REPO = Path(__file__).resolve().parents[2]
V14_BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v14.py"
V14_BUILDER_PATH = REPO / V14_BUILDER_RELATIVE
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v14_base", V14_BUILDER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the Debian gaming v0.14 builder")
V14 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = V14
SPEC.loader.exec_module(V14)
BASE = V14.BASE


README_RELATIVE = "mainline/rootfs-debian13-gaming-v15/README.md"
PRODUCT_DOC_RELATIVE = "mainline/rootfs-debian13-gaming-v15/PRODUCT.md"
IMAGE_TOOL_RELATIVE = "mainline/rootfs-debian13-gaming-v15/image-in-container.sh"
BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v15.py"
TEST_RELATIVE = "mainline/tests/test-debian13-gaming-rootfs-v15.py"

EXTRA_INPUTS = (
    (
        "libretro-genesisplusgx_1.7.4+git20221128-2_arm64.deb",
        REPO / "mainline/out/.cache/r46h-genesisplusgx/libretro-genesisplusgx_1.7.4+git20221128-2_arm64.deb",
        370_312,
        "059f4dbecfc4e3083fd561f22d3bd31dc1c04fd73f4e224d72ab63cbf9087007",
    ),
    (
        "gamelist.gamegear.xml",
        REPO / "mainline/out/r46h-gaming-genesisplusgx-content-v0.1/gamelist.gamegear.xml",
        15_715,
        "dd312a4cdab6e7cab4b0065976d953089fd6456bc788a3657fb1b5f6e0bef28f",
    ),
    (
        "legacy-media-links.tsv",
        REPO / "mainline/out/r46h-gaming-genesisplusgx-content-v0.1/legacy-media-links.tsv",
        456_800,
        "816f3a93f9a90cba5be3a0ef77f1d77ea5bf8e8dce909adb4b0d1bdb1fc8cf78",
    ),
    (
        "r46h-firstboot.v14",
        REPO / "mainline/out/r46h-gaming-genesisplusgx-content-v0.1/v14-inputs/firstboot",
        837,
        "d55be2de759f741db7f3bf6eafd3fdc1da2965c4b539752760f12242bcd1e1bd",
    ),
    (
        "r46h-es-de-ui.v14",
        REPO / "mainline/out/r46h-gaming-genesisplusgx-content-v0.1/v14-inputs/runner",
        9_747,
        "9c7370d4ec82c36126fc058deb3a87b46bdc1572ddece9bad85cf638490eb876",
    ),
    (
        "r46h-screenshot.v14",
        REPO / "mainline/out/r46h-gaming-genesisplusgx-content-v0.1/v14-inputs/screenshot",
        11_281,
        "9b9dae53a2ca8fb13c988f7b01feb8b4816e7448bbe4d14450674d0efd6bf502",
    ),
    (
        "r46h-rootfs-smoke.v14",
        REPO / "mainline/out/r46h-gaming-genesisplusgx-content-v0.1/v14-inputs/smoke",
        8_295,
        "0c2d1a8978455b0f212396ed7f821d7891d1a4c86396a17ef147c49f06be34a0",
    ),
    (
        "system-links.v14.tsv",
        REPO / "mainline/out/r46h-gaming-genesisplusgx-content-v0.1/v14-inputs/system-links.tsv",
        271,
        "78f510702fbfc3995d068b0d06ded3118a88e482cecadddaf29bcef83244acaf",
    ),
    (
        "es-de-systems.v14.xml",
        REPO / "mainline/out/r46h-gaming-genesisplusgx-content-v0.1/v14-inputs/systems.xml",
        6_435,
        "0adeaaa1136ed19d6f3d8326eadb8de356ca081221bf0518b8df93f884bd2e24",
    ),
)

BASE.CACHE_ROOT = BASE.OUTPUT_ROOT / ".cache/r46h-debian13-gaming-rootfs-v15"
BASE.OUTPUT_NAME = "r46h-debian13-p2-gaming-v0.15"
BASE.ARTIFACT_ID = "debian13-p2-gaming-v0.15"
BASE.IMAGE_NAME = f"{BASE.OUTPUT_NAME}.ext4"
BASE.OUTPUT_DIR = BASE.OUTPUT_ROOT / BASE.OUTPUT_NAME
BASE.BASE_FS_UUID = "d3130014-46a4-4d56-9001-000000000014"
BASE.BASE_FS_LABEL = "R46H_GAMING_V14"
BASE.FS_UUID = "d3130015-46a4-4d56-9001-000000000015"
BASE.FS_LABEL = "R46H_GAMING_V15"
BASE.SOURCE_DATE_EPOCH = "1788652800"
BASE.BASE_IMAGE = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.14/r46h-debian13-p2-gaming-v0.14.ext4"
BASE.BASE_IMAGE_SHA256 = "34a52170a7b6d950abd677f7ff3f1c03f87449629047a536a44500efae8efffe"
BASE.BASE_BUILD_INFO = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.14/BUILD-INFO"
BASE.BASE_BUILD_INFO_SHA256 = "6c3319cb983021d55e3f87490937ba3bc432d69f20b8abda47835c3a1d60d8fb"
BASE.BASE_CONSOLIDATED_RECEIPT_SHA256 = "3143cf0856fe86cd20c9bf3cf2b8142261d3b2d8d052c65e7a0c2de518d0b49e"
BASE.BASE_GAMING_RECEIPT_SHA256 = "82721e16a9b9a7c7927d0ca4d228dd3d850e3a39dca245177ec1f016b3b8d314"
BASE.BASE_FIRSTBOOT_SHA256 = "d55be2de759f741db7f3bf6eafd3fdc1da2965c4b539752760f12242bcd1e1bd"
BASE.FINAL_FIRSTBOOT_SHA256 = "8dce1ed4fdd29108359bdbf5c271d058481560e009de94e0b97dad423f08eaec"
BASE.BASE_ROOTFS_SMOKE_SHA256 = "0c2d1a8978455b0f212396ed7f821d7891d1a4c86396a17ef147c49f06be34a0"
BASE.FINAL_ROOTFS_SMOKE_SHA256 = "18bfad35ef7440c4c8df35da6aef1c54a654ff4e7b0153b7a678b98da9635818"
BASE.VERSION_TEXT = "v0.15"
BASE.VERSION_TOKEN = "V15"
BASE.IMAGE_TOOL_RELATIVE = IMAGE_TOOL_RELATIVE
BASE.BASE_IMAGE_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.14.ext4"
BASE.BASE_BUILD_INFO_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.14.BUILD-INFO"
BASE.DEBUGFS_EVIDENCE_NAME = "DEBUGFS-V15.txt"
BASE.INDEPENDENT_DEBUGFS_EVIDENCE_NAME = "INDEPENDENT-DEBUGFS-V15.txt"
BASE.ARTIFACT_STATUS = "host-only-no-media-operation-performed"

BASE.EXTRA_BUILD_ENVIRONMENT = {
    "BASE_CORE_OPTIONS_SHA256": "c7863f5096f2e6226ec7d7a0c37a74d267c87705da197f7f7f43d41fe12a29df",
    "BASE_ES_DE_RECEIPT_SHA256": "84fa6abf90cf0f805142f18f1ca421cc899c6352d79ea1369dd4b72cafdb23ff",
    "BASE_ES_DE_RUNNER_SHA256": "9c7370d4ec82c36126fc058deb3a87b46bdc1572ddece9bad85cf638490eb876",
    "BASE_ES_DE_SYSTEMS_SHA256": "0adeaaa1136ed19d6f3d8326eadb8de356ca081221bf0518b8df93f884bd2e24",
    "BASE_MEDIA_LINKS_SHA256": "8b4820cf09a61fdc0fe96c638aad867c2af0013aa3a62187ef161dd54b0e86c1",
    "BASE_RETROARCH_APPEND_SHA256": "d9bb66ae213d5ef30da941f238322640103af69252c5a6d2bf4f9838ee756975",
    "BASE_SCREENSHOT_SHA256": "9b9dae53a2ca8fb13c988f7b01feb8b4816e7448bbe4d14450674d0efd6bf502",
    "BASE_SETTINGS_SHA256": "7162192575638a0ae46655a15929e6a926dd21334567f837c8ef7d9bba42ad01",
    "BASE_SYSTEM_LINKS_SHA256": "78f510702fbfc3995d068b0d06ded3118a88e482cecadddaf29bcef83244acaf",
    "CORE_OPTIONS_SHA256": "c7863f5096f2e6226ec7d7a0c37a74d267c87705da197f7f7f43d41fe12a29df",
    "ES_DE_RECEIPT_SHA256": "bd81e5c90d9459d600e8bbb3c370081d1a55a0dd404001c62cf7598929a87a66",
    "ES_DE_RUNNER_SHA256": "973b2e09a16501d549debf580dd5876925781283c6d67973bc345c64fcad203a",
    "ES_DE_SYSTEMS_SHA256": "8d372623c8dc910325e1773bac8da6acdc99d10b2a08f9b7eaf42d095bf3b180",
    "FBNEO_FULL_CORE_SHA256": "d63bc891a85599949b99748aa5dcd79aed86c29dc859739a9bfe4e1361c02956",
    "FILTERED_DREAMCAST_GAMELIST_SHA256": "0099df582b7c4157dfed1ebe9ecf161efc8a3ab799630dc06977adafdffc7927",
    "FILTERED_GAMEGEAR_GAMELIST_SHA256": EXTRA_INPUTS[1][3],
    "FILTERED_PSP_GAMELIST_SHA256": "c2f722c494fa623f9b31b7c9a4eab1fa0aca9409262fa82d2631dbc728ed5288",
    "FLYCAST_BUNDLE_SHA256": "2e526c2533cf9e9ac79e210226c1a5e96990b9f6463317d747175604b8280861",
    "FLYCAST_CORE_SHA256": "1de0ebcad7de5906b2e03e3b7885254635399503969b5e1c8b21c8ef79c07eaf",
    "GENESISPLUSGX_CORE_SHA256": "f143cdc25c10acd0c5695ef11c7aaa7a42936fda426a9eec6dd4a248f5c73546",
    "GENESISPLUSGX_PACKAGE_SHA256": EXTRA_INPUTS[0][3],
    "GAMING_PAYLOAD_ID": BASE.GAMING_PAYLOAD_ID,
    "MEDIA_LINKS_SHA256": EXTRA_INPUTS[2][3],
    "PPSSPP_ASSETS_MANIFEST_SHA256": "98c8b6f16f9fe7f8def8c78a1f2b48b62744ee8b45afa4cf5c65b3c0fce80abb",
    "PPSSPP_BUNDLE_SHA256": "8940315762f7abb91624d009f13cddafdb1ab644e41f8e4bf3be70a5a875bc04",
    "PPSSPP_CORE_SHA256": "f39819580dc5a867bd8674eef37b13c2eef328824b1aabe7ed4dc98af61bf3a7",
    "RETROARCH_APPEND_SHA256": "d9bb66ae213d5ef30da941f238322640103af69252c5a6d2bf4f9838ee756975",
    "SCREENSHOT_SHA256": "b7b57c6425bc95402f70ce6527a0bf523ad3ccf9aafd91ebd18c141ebeb75db7",
    "SYSTEM_LINKS_SHA256": "b9f0cedb38437d9ab080631e0a8c3d23316f949b1d715043cbfdb1c9002dccf9",
}
BASE.EXTRA_BUILD_INFO = {
    "consolidated_frontend": "ES-DE-3.4.1-r51",
    "consolidated_media_link_count": "6220",
    "consolidated_media_link_delta": "105",
    "consolidated_media_missing_host_fixture": "2501",
    "consolidated_remote_input_actions": "16",
    "consolidated_system_count": "14",
    "es_de_core_options_sha256": BASE.EXTRA_BUILD_ENVIRONMENT["CORE_OPTIONS_SHA256"],
    "es_de_settings_sha256": BASE.EXTRA_BUILD_ENVIRONMENT["BASE_SETTINGS_SHA256"],
    "filtered_dreamcast_gamelist_sha256": BASE.EXTRA_BUILD_ENVIRONMENT["FILTERED_DREAMCAST_GAMELIST_SHA256"],
    "filtered_gamegear_gamelist_sha256": EXTRA_INPUTS[1][3],
    "flycast_bundle_sha256": BASE.EXTRA_BUILD_ENVIRONMENT["FLYCAST_BUNDLE_SHA256"],
    "flycast_core_sha256": BASE.EXTRA_BUILD_ENVIRONMENT["FLYCAST_CORE_SHA256"],
    "flycast_host_load_samples": "14",
    "genesisplusgx_core_sha256": BASE.EXTRA_BUILD_ENVIRONMENT["GENESISPLUSGX_CORE_SHA256"],
    "genesisplusgx_host_load_samples": "105",
    "genesisplusgx_package_sha256": EXTRA_INPUTS[0][3],
    "legacy_media_links_sha256": EXTRA_INPUTS[2][3],
    "ppsspp_assets_manifest_sha256": BASE.EXTRA_BUILD_ENVIRONMENT["PPSSPP_ASSETS_MANIFEST_SHA256"],
    "ppsspp_bundle_sha256": BASE.EXTRA_BUILD_ENVIRONMENT["PPSSPP_BUNDLE_SHA256"],
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
    "successor_base_artifact_id=debian13-p2-gaming-v0.14",
    "consolidated_frontend=ES-DE-3.4.1-r51",
    "consolidated_media_link_count=6220",
    "consolidated_media_link_delta=105",
    "consolidated_media_missing_host_fixture=2501",
    "consolidated_system_count=14",
    "consolidated_remote_input_actions=16",
    "flycast_host_load_samples=14",
    "genesisplusgx_host_load_samples=105",
    "ppsspp_host_load_samples=6",
    f"es_de_core_options_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['CORE_OPTIONS_SHA256']}",
    f"es_de_systems_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['ES_DE_SYSTEMS_SHA256']}",
    f"es_de_system_links_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['SYSTEM_LINKS_SHA256']}",
    f"filtered_dreamcast_gamelist_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['FILTERED_DREAMCAST_GAMELIST_SHA256']}",
    f"filtered_gamegear_gamelist_sha256={EXTRA_INPUTS[1][3]}",
    f"flycast_bundle_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['FLYCAST_BUNDLE_SHA256']}",
    f"flycast_core_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['FLYCAST_CORE_SHA256']}",
    f"genesisplusgx_core_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['GENESISPLUSGX_CORE_SHA256']}",
    f"genesisplusgx_package_sha256={EXTRA_INPUTS[0][3]}",
    f"legacy_media_links_sha256={EXTRA_INPUTS[2][3]}",
    f"ppsspp_assets_manifest_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['PPSSPP_ASSETS_MANIFEST_SHA256']}",
    f"ppsspp_bundle_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['PPSSPP_BUNDLE_SHA256']}",
    f"ppsspp_core_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['PPSSPP_CORE_SHA256']}",
    "remote_pairing=required-after-image-write",
)
BASE.SOURCE_PATHS = (
    README_RELATIVE,
    PRODUCT_DOC_RELATIVE,
    IMAGE_TOOL_RELATIVE,
    BUILDER_RELATIVE,
    TEST_RELATIVE,
    "mainline/gaming-genesisplusgx/README.md",
    "mainline/gaming-genesisplusgx/content-audit.json",
    "mainline/gaming-genesisplusgx/es-system.gamegear.xml",
    "mainline/gaming-genesisplusgx/generate-filtered-gamelist.py",
    "mainline/gaming-genesisplusgx/package-lock.json",
    "mainline/gaming-genesisplusgx/system-link.gamegear.tsv",
    "mainline/gaming-genesisplusgx/transform-es-de-runner.awk",
    *BASE.SOURCE_PATHS,
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
    "FLYCAST-VERIFY.txt",
    "GENESISPLUSGX-VERIFY.txt",
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
    "FLYCAST-VERIFY.txt": "INDEPENDENT-FLYCAST-VERIFY.txt",
    "GENESISPLUSGX-VERIFY.txt": "INDEPENDENT-GENESISPLUSGX-VERIFY.txt",
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
BASE.STAGE_RE = re.compile(r"^\.r46h-debian13-p2-gaming-v0\.15\.tmp\.[A-Za-z0-9_]+$")

_validate_inputs = V14._validate_inputs
_write_build_metadata = V14._write_build_metadata
_validate_stage = V14._validate_stage


def validate_inputs(docker: str, extraction_root: Path) -> Path:
    payload = _validate_inputs(docker, extraction_root)
    destination = payload / "product-inputs"
    destination.mkdir(mode=0o700)
    for name, path, size, digest in EXTRA_INPUTS:
        metadata = BASE.require_regular(path, f"v0.15 product input {name}")
        if metadata.st_size != size or BASE.sha256_file(path) != digest:
            raise BASE.BuildError(f"v0.15 product input mismatch: {name}")
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
        raise BASE.BuildError("v0.15 product input receipt mismatch")
    for name in ("MEDIA-VERIFY.txt", "INDEPENDENT-MEDIA-VERIFY.txt"):
        if "R46H_V15_MEDIA_VERIFY_RESULT=pass" not in (stage / name).read_text(
            encoding="utf-8", errors="replace"
        ):
            raise BASE.BuildError(f"v0.15 media verification marker missing: {name}")
    for name in ("FLYCAST-VERIFY.txt", "INDEPENDENT-FLYCAST-VERIFY.txt"):
        if "R46H_V15_FLYCAST_VERIFY_RESULT=pass" not in (stage / name).read_text(
            encoding="utf-8", errors="replace"
        ):
            raise BASE.BuildError(f"v0.15 Flycast verification marker missing: {name}")
    for name in ("GENESISPLUSGX-VERIFY.txt", "INDEPENDENT-GENESISPLUSGX-VERIFY.txt"):
        if "R46H_V15_GENESISPLUSGX_VERIFY_RESULT=pass" not in (stage / name).read_text(
            encoding="utf-8", errors="replace"
        ):
            raise BASE.BuildError(f"v0.15 Genesis Plus GX verification marker missing: {name}")
    for name in ("PRODUCT-VERIFY.txt", "INDEPENDENT-PRODUCT-VERIFY.txt"):
        if "R46H_V15_PRODUCT_VERIFY_RESULT=pass" not in (stage / name).read_text(
            encoding="utf-8", errors="replace"
        ):
            raise BASE.BuildError(f"v0.15 product verification marker missing: {name}")
    return image_sha256


BASE.validate_inputs = validate_inputs
BASE.write_build_metadata = write_build_metadata
BASE.validate_stage = validate_stage


if __name__ == "__main__":
    raise SystemExit(BASE.main())
