#!/usr/bin/env python3
"""Build the rollback-safe persistent integration of the accepted v0.17 DTB."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
BASE_BUILDER_RELATIVE = "mainline/scripts/build-r46h-v16-boot-promotion.py"
BASE_BUILDER_PATH = REPO / BASE_BUILDER_RELATIVE
SPEC = importlib.util.spec_from_file_location("r46h_v16_boot_builder_base", BASE_BUILDER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the v0.16 BOOT promotion builder")
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)


PREVIOUS_BASE_P1_SHA256 = (
    "042ad4ad08f39f60f1d57e393ab32ae148e2a946ab9996822ae161934f7a0825"
)
CURRENT_BASE_P1_SHA256 = (
    "7d3197852284c7feaf0034489310cbe4eb14cb73f79b4b94b733b1cac004a18e"
)
PREVIOUS_V16_DTB_NAME = "rk3326-r46h-mainline-v0.16-disable-secondary.dtb"
PREVIOUS_V16_DTB_SIZE = 49_522
PREVIOUS_V16_DTB_SHA256 = (
    "7831617d4003cdbb2733433781f80625cb94e7c9d619f2f90990223b8f8d7f81"
)
PREVIOUS_V16_BOOT_NAME = "boot.ini.v0.16-disable-secondary"
PREVIOUS_V16_BOOT_SIZE = 1_449
PREVIOUS_V16_BOOT_SHA256 = (
    "edb33de5fef23b810deec13c05b6958a72eea3dbb74ce2b39b0f80cdb508aba3"
)


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise BASE.BuildError(f"template marker count mismatch: {old}")
    return text.replace(old, new, 1)


def render_payload_source(relative: str, payload: bytes) -> bytes:
    if relative not in {BASE.INSTALL_RELATIVE, BASE.TRANSACTION_RELATIVE}:
        return payload
    text = payload.decode("utf-8")
    for old, new in (
        ("v0.16-disable-secondary", "v0.17-power-settle"),
        ("r46h-v16-boot-promotion", "r46h-v17-boot-promotion"),
        ("R46H_V16", "R46H_V17"),
        ("V0.16", "V0.17"),
        ("v0.16", "v0.17"),
        ("V16", "V17"),
        ("v16", "v17"),
        (PREVIOUS_BASE_P1_SHA256, CURRENT_BASE_P1_SHA256),
    ):
        text = text.replace(old, new)
    for old, new in (
        (
            f"readonly R46H_V17_DTB_SIZE={PREVIOUS_V16_DTB_SIZE}",
            f"readonly R46H_V17_DTB_SIZE={BASE.CANDIDATE_DTB_SIZE}",
        ),
        (
            f"readonly R46H_V17_DTB_SHA256={PREVIOUS_V16_DTB_SHA256}",
            f"readonly R46H_V17_DTB_SHA256={BASE.CANDIDATE_DTB_SHA256}",
        ),
        (
            f"readonly R46H_V17_BOOT_SIZE={PREVIOUS_V16_BOOT_SIZE}",
            f"readonly R46H_V17_BOOT_SIZE={BASE.BOOT_SIZE}",
        ),
        (
            f"readonly R46H_V17_BOOT_SHA256={PREVIOUS_V16_BOOT_SHA256}",
            f"readonly R46H_V17_BOOT_SHA256={BASE.BOOT_SHA256}",
        ),
    ):
        if old in text:
            text = replace_once(text, old, new)
    if relative == BASE.INSTALL_RELATIVE:
        live_status_anchor = (
            '  [[ "$(tr -d \'\\0\' < /proc/device-tree/mmc@ff370000/status)" '
            '== okay ]] || \\\n'
            "    die 'live system MMC status mismatch'\n"
        )
        live_delay_check = (
            '  [[ -f /proc/device-tree/mmc@ff370000/post-power-on-delay-ms ]] || \\\n'
            "    die 'live system MMC power-settle property is missing'\n"
            '  [[ "$(od -An -tx1 '
            '/proc/device-tree/mmc@ff370000/post-power-on-delay-ms | '
            'tr -d \'[:space:]\')" == 00000320 ]] || \\\n'
            "    die 'live system MMC power-settle property mismatch'\n"
        )
        text = replace_once(
            text,
            live_status_anchor,
            live_status_anchor + live_delay_check,
        )
        return text.encode("utf-8")

    candidate_constants = (
        f"readonly R46H_V17_BOOT_SHA256={BASE.BOOT_SHA256}\n"
    )
    predecessor_constants = (
        f"readonly R46H_PREVIOUS_V16_DTB_NAME={PREVIOUS_V16_DTB_NAME}\n"
        f"readonly R46H_PREVIOUS_V16_DTB_SIZE={PREVIOUS_V16_DTB_SIZE}\n"
        f"readonly R46H_PREVIOUS_V16_DTB_SHA256={PREVIOUS_V16_DTB_SHA256}\n"
        f"readonly R46H_PREVIOUS_V16_BOOT_NAME={PREVIOUS_V16_BOOT_NAME}\n"
        f"readonly R46H_PREVIOUS_V16_BOOT_SIZE={PREVIOUS_V16_BOOT_SIZE}\n"
        f"readonly R46H_PREVIOUS_V16_BOOT_SHA256={PREVIOUS_V16_BOOT_SHA256}\n"
    )
    text = replace_once(
        text,
        candidate_constants,
        candidate_constants + predecessor_constants,
    )
    text = replace_once(
        text,
        "readonly R46H_BASE_TOP_LEVEL_COUNT=29",
        "readonly R46H_BASE_TOP_LEVEL_COUNT=31",
    )
    text = replace_once(
        text,
        "rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb|uInitrd) return 0 ;;",
        "rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb|\\\n"
        f"    {PREVIOUS_V16_BOOT_NAME}|{PREVIOUS_V16_DTB_NAME}|uInitrd) return 0 ;;",
    )
    text = replace_once(
        text,
        '    "$R46H_V15_BOOT_NAME" "$R46H_V15_IMAGE_NAME" "$R46H_V15_DTB_NAME"; do',
        '    "$R46H_V15_BOOT_NAME" "$R46H_V15_IMAGE_NAME" "$R46H_V15_DTB_NAME" \\\n'
        '    "$R46H_PREVIOUS_V16_BOOT_NAME" "$R46H_PREVIOUS_V16_DTB_NAME"; do',
    )
    anchor = (
        '  r46h_tx_check_file "$boot/$R46H_V15_DTB_NAME" "$R46H_V15_DTB_SIZE" \\\n'
        '    "$R46H_V15_DTB_SHA256" \'v0.15 fallback DTB\' || return\n'
    )
    predecessor_checks = (
        '  r46h_tx_check_file "$boot/$R46H_PREVIOUS_V16_BOOT_NAME" '
        '"$R46H_PREVIOUS_V16_BOOT_SIZE" \\\n'
        '    "$R46H_PREVIOUS_V16_BOOT_SHA256" \'inert v0.16 boot script\' || return\n'
        '  r46h_tx_check_file "$boot/$R46H_PREVIOUS_V16_DTB_NAME" '
        '"$R46H_PREVIOUS_V16_DTB_SIZE" \\\n'
        '    "$R46H_PREVIOUS_V16_DTB_SHA256" \'inert v0.16 DTB\' || return\n'
    )
    text = replace_once(text, anchor, anchor + predecessor_checks)
    return text.encode("utf-8")


def configure_base() -> None:
    promotion_relative = "mainline/gaming-product-v17-boot-promotion"
    base_values = {
        "VERSION_LABEL": "v0.17",
        "PROMOTION_RELATIVE": promotion_relative,
        "README_RELATIVE": f"{promotion_relative}/README.md",
        "BOOT_RELATIVE": f"{promotion_relative}/boot.ini.v0.17-power-settle",
        "BUILDER_RELATIVE": "mainline/scripts/build-r46h-v17-boot-promotion.py",
        "TEST_RELATIVE": "mainline/tests/test-r46h-v17-boot-promotion.py",
        "ONE_SHOT_RUNBOOK_RELATIVE": "mainline/bringup-tests/V17-MMC-POWER-SETTLE.md",
        "ONE_SHOT_TEST_RELATIVE": "mainline/tests/test-r46h-v17-mmc-power-settle.py",
        "PROMOTION": REPO / promotion_relative,
        "CACHE_ROOT": REPO / "mainline/out/.cache/r46h-v17-boot-promotion",
        "RELEASE_ROOT": REPO / "mainline/out/r46h-v17-boot-promotion",
        "PAYLOAD_ID": "r46h-v17-boot-promotion-v0.1",
        "SOURCE_DATE_EPOCH": 1_787_616_000,
        "FROZEN_CANDIDATE": (
            REPO
            / "mainline/out/r46h-v17-mmc-power-settle"
            / "r46h-v17-mmc-power-settle.tar.gz"
        ),
        "FROZEN_CANDIDATE_SIZE": 12_517,
        "FROZEN_CANDIDATE_SHA256": (
            "02b6da57c039c31a95143eab1b922c14c0ac4bc60621d02dab9d07f1796409a9"
        ),
        "FROZEN_CANDIDATE_ROOT": "v0.17-800ms-single-host",
        "CANDIDATE_DTB_NAME": "rk3326-r46h-mainline-v0.17-power-settle.dtb",
        "CANDIDATE_DTB_SIZE": 49_561,
        "CANDIDATE_DTB_SHA256": (
            "116942e7bc8691bbf6bf185dd3cbe306de2d33be8dad79a027249f9f5234b796"
        ),
        "BOOT_NAME": "boot.ini.v0.17-power-settle",
        "BOOT_SIZE": 1_417,
        "BOOT_SHA256": (
            "96300e2e74fa3ea00da28d81c80c7fa3e327bd4784af6ddc766817b36ad33778"
        ),
        "BASE_P1_SHA256": CURRENT_BASE_P1_SHA256,
        "CANDIDATE_VARIABLE_PREFIX": "R46H_V17",
        "CANDIDATE_DTB_EXTRA_CHECKS": (
            'test "$(fdtget -t u /work/candidate.dtb /mmc@ff370000 '
            'post-power-on-delay-ms)" = 800'
        ),
    }
    for name, value in base_values.items():
        setattr(BASE, name, value)
    BASE.ARCHIVE_NAME = f"{BASE.PAYLOAD_ID}.tar.gz"
    BASE.CANDIDATE_MEMBER = f"{BASE.FROZEN_CANDIDATE_ROOT}/R46H.DTB"
    BASE.FROZEN_CANDIDATE_FILES = (
        "LAUNCH.txt",
        "R46H-V17.SCR",
        "R46H.DTB",
        "RECEIPT.json",
        "SHA256SUMS",
        "UBOOT-CMDS.txt",
        "r46h-v17-mmc-power-settle.dtbo",
    )
    BASE.SOURCE_PATHS = (
        BASE.ONE_SHOT_RUNBOOK_RELATIVE,
        BASE.README_RELATIVE,
        BASE.BOOT_RELATIVE,
        BASE.INSTALL_RELATIVE,
        BASE.TRANSACTION_RELATIVE,
        BASE.FALLBACK_HELPER_RELATIVE,
        BASE.STORAGE_HELPER_RELATIVE,
        BASE.BUILDER_RELATIVE,
        BASE.TEST_RELATIVE,
        BASE.ONE_SHOT_TEST_RELATIVE,
        BASE_BUILDER_RELATIVE,
        "mainline/tests/test-r46h-v16-boot-promotion.py",
    )
    BASE.PAYLOAD_MEMBERS = {
        "PAYLOAD-INFO.json",
        "PAYLOAD.COMPLETE",
        "SHA256SUMS",
        "fallback-modules.sh",
        "files",
        f"files/{BASE.BOOT_NAME}",
        f"files/{BASE.CANDIDATE_DTB_NAME}",
        "install.sh",
        "storage-health.sh",
        "transaction.sh",
    }
    BASE.GENERATION_MEMBERS = {
        BASE.ARCHIVE_NAME,
        "BUILD-COMPLETE",
        "BUILD-RECEIPT.json",
        "SHA256SUMS",
        "SOURCE-MANIFEST.json",
    }
    BASE.render_payload_source = render_payload_source


configure_base()


def __getattr__(name: str):
    return getattr(BASE, name)


if __name__ == "__main__":
    raise SystemExit(BASE.main())
