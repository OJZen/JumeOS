#!/usr/bin/env python3
"""Build the host-only R46H Debian 13 gaming p2 v0.7 successor."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]
BASE_BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v06.py"
BASE_BUILDER_PATH = REPO / BASE_BUILDER_RELATIVE
SPEC = importlib.util.spec_from_file_location(
    "debian13_gaming_rootfs_successor_base", BASE_BUILDER_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the Debian gaming successor builder")
BASE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BASE
SPEC.loader.exec_module(BASE)


README_RELATIVE = "mainline/rootfs-debian13-gaming-v07/README.md"
IMAGE_TOOL_RELATIVE = "mainline/rootfs-debian13-gaming-v07/image-in-container.sh"
BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v07.py"
TEST_RELATIVE = "mainline/tests/test-debian13-gaming-rootfs-v07.py"

BASE.CACHE_ROOT = BASE.OUTPUT_ROOT / ".cache/r46h-debian13-gaming-rootfs-v07"
BASE.OUTPUT_NAME = "r46h-debian13-p2-gaming-v0.7"
BASE.ARTIFACT_ID = "debian13-p2-gaming-v0.7"
BASE.IMAGE_NAME = f"{BASE.OUTPUT_NAME}.ext4"
BASE.OUTPUT_DIR = BASE.OUTPUT_ROOT / BASE.OUTPUT_NAME

BASE.BASE_FS_UUID = "d3130006-46a4-4d56-9001-000000000006"
BASE.BASE_FS_LABEL = "R46H_GAMING_V06"
BASE.FS_UUID = "d3130007-46a4-4d56-9001-000000000007"
BASE.FS_LABEL = "R46H_GAMING_V07"
BASE.SOURCE_DATE_EPOCH = "1788048000"
BASE.BASE_IMAGE = (
    BASE.OUTPUT_ROOT
    / "r46h-debian13-p2-gaming-v0.6"
    / "r46h-debian13-p2-gaming-v0.6.ext4"
)
BASE.BASE_IMAGE_SHA256 = (
    "4ac3a525264fcab7efda804c147f8e77604cbee82847d504de7e359258ca4bee"
)
BASE.BASE_BUILD_INFO = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.6/BUILD-INFO"
BASE.BASE_BUILD_INFO_SHA256 = (
    "a7219d27d78be4b6b6f34b5dae72cf6e5d259c5aacf5a35a878b6cce0572c463"
)
BASE.BASE_CONSOLIDATED_RECEIPT_SHA256 = (
    "92c82cd04d3c9a383163d9973997a283500fd615040b038b744d4d79000f4681"
)
BASE.BASE_GAMING_RECEIPT_SHA256 = (
    "5cdfa424a28858a91e0344f0544e962c5aa0258bb3a7ea41db76df16c77da5d1"
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
    "3c065d08ee2ee89d48fba0b4432662dd9d51e3e5d7a06212a854c758d55b504c"
)
BASE.FINAL_FIRSTBOOT_SHA256 = (
    "3e4ea0389887c508e4bbcdbae2e07c19018d2777c55256bbbfa596255ffda72d"
)
BASE.BASE_ROOTFS_SMOKE_SHA256 = (
    "825e7a12667770f83d0e0ba79363a4d4b2ae6c5fab068aaa1eb4b5d7aa3034c7"
)
BASE.FINAL_ROOTFS_SMOKE_SHA256 = (
    "b5d04865dcff63c6e8221d7d5ee2261000459f906bbdca2231b98cc1c2bb51cb"
)

BASE.VERSION_TEXT = "v0.7"
BASE.VERSION_TOKEN = "V07"
BASE.GAMING_PAYLOAD_VERSION_TEXT = "v0.6"
BASE.IMAGE_TOOL_RELATIVE = IMAGE_TOOL_RELATIVE
BASE.BASE_IMAGE_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.6.ext4"
BASE.BASE_BUILD_INFO_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.6.BUILD-INFO"
BASE.DEBUGFS_EVIDENCE_NAME = "DEBUGFS-V07.txt"
BASE.INDEPENDENT_DEBUGFS_EVIDENCE_NAME = "INDEPENDENT-DEBUGFS-V07.txt"
BASE.ARTIFACT_STATUS = "host-only-no-media-operation-performed"
BASE.EXTRA_BUILD_ENVIRONMENT = {
    "FINAL_CONDITION_SHA256": (
        "9071bae4b9ab83c89ea55ed80c8601d214ab8d479f7dd9168ac4b7a5134dbc03"
    ),
    "FINAL_GAMING_RECEIPT_SHA256": (
        "82721e16a9b9a7c7927d0ca4d228dd3d850e3a39dca245177ec1f016b3b8d314"
    ),
    "FINAL_PRODUCT_DOC_SHA256": (
        "13442f13edb852c48e05dc548c2aec1656be4debbe7be52617d2527bdbd494c0"
    ),
    "FINAL_RUNNER_SHA256": (
        "27d2f987545a3ab20610806923372b41530d41e5e3fc0384614211088d71135c"
    ),
    "FSTAB_SHA256": (
        "390d3e67cfaa42aa2781b06c0bb167cae961034d22563584c58ae57e0d5cada5"
    ),
    "PREVIOUS_CONDITION_SHA256": (
        "888a44d822030430924b012c81069c117c842e17a5173711d6a85e7d351b6031"
    ),
    "PREVIOUS_PRODUCT_DOC_SHA256": (
        "fdf2be72c5c12c57e48a3082a51ecc8b6da09188a627ceece698b0d481d7d3db"
    ),
    "PREVIOUS_RECEIPT_SHA256": BASE.BASE_GAMING_RECEIPT_SHA256,
    "PREVIOUS_RUNNER_SHA256": (
        "3db31b4c205f98377a56822320f2c63dabce685387becdcb4824fec092ce3133"
    ),
    "ROLLBACK_INFO_SHA256": (
        "2c0b0534d383c6e74877d1125e9946f5641132d649cfff7622b3e7ceaa055059"
    ),
    "ROLLBACK_MANIFEST_SHA256": (
        "cab1619dd8bfbcc022a5b33daea49020b24c197cfda793831c6afaed90f1bdbf"
    ),
}
BASE.EXTRA_BUILD_INFO = {
    "gaming_overlay_file_count": "3",
    "gaming_previous_receipt_sha256": BASE.BASE_GAMING_RECEIPT_SHA256,
    "gaming_receipt_sha256": BASE.EXTRA_BUILD_ENVIRONMENT[
        "FINAL_GAMING_RECEIPT_SHA256"
    ],
    "gaming_rollback_manifest_sha256": BASE.EXTRA_BUILD_ENVIRONMENT[
        "ROLLBACK_MANIFEST_SHA256"
    ],
}
BASE.CONSOLIDATED_RECEIPT_EXTRA_MARKERS = (
    "successor_base_artifact_id=debian13-p2-gaming-v0.6",
    "gaming_payload_id=r46h-gaming-mvp-v0.6",
    "gaming_previous_payload_id=r46h-gaming-mvp-v0.5",
    f"gaming_previous_receipt_sha256={BASE.BASE_GAMING_RECEIPT_SHA256}",
    (
        "gaming_receipt_sha256="
        f"{BASE.EXTRA_BUILD_ENVIRONMENT['FINAL_GAMING_RECEIPT_SHA256']}"
    ),
    "gaming_overlay_file_count=3",
    "gaming_rollback_state=/var/lib/r46h/gaming-mvp-v0.6-rollback",
    (
        "gaming_rollback_info_sha256="
        f"{BASE.EXTRA_BUILD_ENVIRONMENT['ROLLBACK_INFO_SHA256']}"
    ),
    (
        "gaming_rollback_manifest_sha256="
        f"{BASE.EXTRA_BUILD_ENVIRONMENT['ROLLBACK_MANIFEST_SHA256']}"
    ),
)

BASE.SOURCE_PATHS = (
    README_RELATIVE,
    IMAGE_TOOL_RELATIVE,
    BUILDER_RELATIVE,
    TEST_RELATIVE,
    BASE_BUILDER_RELATIVE,
    "mainline/deploy/profiles/hl-r46h-v22-g92-v1.json",
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
    "ROLLBACK-STATE.sha256",
    "SYSTEMD-VERIFY.txt",
    "TUNE2FS.txt",
    "UDEV-VERIFY.txt",
}
BASE.INDEPENDENT_EVIDENCE = {
    BASE.DEBUGFS_EVIDENCE_NAME: BASE.INDEPENDENT_DEBUGFS_EVIDENCE_NAME,
    "E2FSCK.txt": "INDEPENDENT-E2FSCK.txt",
    "EXT4-VERIFIED.sha256": "INDEPENDENT-EXT4-VERIFIED.sha256",
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
        "REPRODUCE.txt",
        "SHA256SUMS",
        "SOURCE-MANIFEST.json",
        BASE.IMAGE_NAME,
    }
)
BASE.STAGE_RE = BASE.re.compile(
    r"^\.r46h-debian13-p2-gaming-v0\.7\.tmp\.[A-Za-z0-9]+$"
)


def main() -> int:
    return BASE.main()


if __name__ == "__main__":
    raise SystemExit(main())
