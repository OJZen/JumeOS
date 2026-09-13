#!/usr/bin/env python3
"""Build the host-only R46H gaming p2 v0.16 runtime-fix successor."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import sys


REPO = Path(__file__).resolve().parents[2]
V15_BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v15.py"
V15_BUILDER_PATH = REPO / V15_BUILDER_RELATIVE
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v15_base", V15_BUILDER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the Debian gaming v0.15 builder")
V15 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = V15
SPEC.loader.exec_module(V15)
BASE = V15.BASE


README_RELATIVE = "mainline/rootfs-debian13-gaming-v16/README.md"
PRODUCT_DOC_RELATIVE = "mainline/rootfs-debian13-gaming-v16/PRODUCT.md"
IMAGE_TOOL_RELATIVE = "mainline/rootfs-debian13-gaming-v16/image-in-container.sh"
BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v16.py"
TEST_RELATIVE = "mainline/tests/test-debian13-gaming-rootfs-v16.py"
REMOTE_INPUT_SOURCE = REPO / "mainline/gaming-remote-input/r46h-remote-input.c"
SCREENSHOT_SOURCE = REPO / "mainline/gaming-remote-screen/r46h-screenshot"
DREAMCAST_FRAGMENT = REPO / "mainline/gaming-flycast/es-system.dreamcast.xml"
REMOTE_INPUT_BUILDER = "sha256:3686fd20408cf746c1171e9345fd6c842a71f87e589f691b2455435b3bdd141a"

GENERATED_INPUTS = (
    ("es-de-systems.v16.xml", 6_435, "d5a5dbd26201907444267247efaee4a3e93fe504873c5dbf11683496d9effc5b"),
    ("r46h-es-de-ui.v16", 10_026, "99bc8e1f71d3fb08c4e9e5199748363068e9eb0ac2a2611131f8b0b1830b62dd"),
    ("r46h-screenshot.v16", 11_371, "d96cecf54d4ad939b18920526755a7d3960fd62299c9805f69fc931a7ccac287"),
    ("r46h-remote-input-10ms", 67_480, "f4204f693a98d957ad8b785d292d5ca8e28298a7d5cf9ac3f7e2be5115d59864"),
    ("r46h-firstboot.v16", 837, "ea4c63a4587378e5b4b42cd5c3f8a5b5bb3847c3630c37d953a6666dbca5b059"),
    ("r46h-rootfs-smoke.v16", 8_295, "dced58913acde7d570b8bd9f49a94a8fc585022c82f63963d81b6342bb578814"),
    ("es-de-receipt.v16", 2_591, "b88c6649e707f6f2acbc19e05482b3e8014f9349fdaedc09e316ad24d5f11910"),
)

BASE.CACHE_ROOT = BASE.OUTPUT_ROOT / ".cache/r46h-debian13-gaming-rootfs-v16"
BASE.OUTPUT_NAME = "r46h-debian13-p2-gaming-v0.16"
BASE.ARTIFACT_ID = "debian13-p2-gaming-v0.16"
BASE.IMAGE_NAME = f"{BASE.OUTPUT_NAME}.ext4"
BASE.OUTPUT_DIR = BASE.OUTPUT_ROOT / BASE.OUTPUT_NAME
BASE.BASE_FS_UUID = "d3130015-46a4-4d56-9001-000000000015"
BASE.BASE_FS_LABEL = "R46H_GAMING_V15"
BASE.FS_UUID = "d3130016-46a4-4d56-9001-000000000016"
BASE.FS_LABEL = "R46H_GAMING_V16"
BASE.SOURCE_DATE_EPOCH = "1788739200"
BASE.BASE_IMAGE = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.15/r46h-debian13-p2-gaming-v0.15.ext4"
BASE.BASE_IMAGE_SHA256 = "a69c2dafeae76f37a6e582bfdf4887d5714b82a4cf5b3dc7a84e29f36be6e893"
BASE.BASE_BUILD_INFO = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.15/BUILD-INFO"
BASE.BASE_BUILD_INFO_SHA256 = "f6533599f9c94997438170ac38e5a49eec9b13aa216cb20cde797cbf952968d0"
BASE.BASE_CONSOLIDATED_RECEIPT_SHA256 = "7a3d4fa07e4a34f9313e1fd4a84c66389cbb7a9cfc740659f241461e4a01524d"
BASE.BASE_GAMING_RECEIPT_SHA256 = "82721e16a9b9a7c7927d0ca4d228dd3d850e3a39dca245177ec1f016b3b8d314"
BASE.BASE_FIRSTBOOT_SHA256 = "8dce1ed4fdd29108359bdbf5c271d058481560e009de94e0b97dad423f08eaec"
BASE.FINAL_FIRSTBOOT_SHA256 = GENERATED_INPUTS[4][2]
BASE.BASE_ROOTFS_SMOKE_SHA256 = "18bfad35ef7440c4c8df35da6aef1c54a654ff4e7b0153b7a678b98da9635818"
BASE.FINAL_ROOTFS_SMOKE_SHA256 = GENERATED_INPUTS[5][2]
BASE.VERSION_TEXT = "v0.16"
BASE.VERSION_TOKEN = "V16"
BASE.IMAGE_TOOL_RELATIVE = IMAGE_TOOL_RELATIVE
BASE.BASE_IMAGE_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.15.ext4"
BASE.BASE_BUILD_INFO_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.15.BUILD-INFO"
BASE.DEBUGFS_EVIDENCE_NAME = "DEBUGFS-V16.txt"
BASE.INDEPENDENT_DEBUGFS_EVIDENCE_NAME = "INDEPENDENT-DEBUGFS-V16.txt"
BASE.ARTIFACT_STATUS = "host-only-no-media-operation-performed"

BASE.EXTRA_BUILD_ENVIRONMENT = {
    "BASE_ES_DE_RECEIPT_SHA256": "bd81e5c90d9459d600e8bbb3c370081d1a55a0dd404001c62cf7598929a87a66",
    "BASE_ES_DE_RUNNER_SHA256": "973b2e09a16501d549debf580dd5876925781283c6d67973bc345c64fcad203a",
    "BASE_ES_DE_SYSTEMS_SHA256": "8d372623c8dc910325e1773bac8da6acdc99d10b2a08f9b7eaf42d095bf3b180",
    "BASE_REMOTE_INPUT_SHA256": "9907972995127792b75f0cf9922c3d750e8a06437b3d4d026f4a1db614f0232c",
    "BASE_SCREENSHOT_SHA256": "b7b57c6425bc95402f70ce6527a0bf523ad3ccf9aafd91ebd18c141ebeb75db7",
    "DREAMCAST_GAMELIST_SHA256": "0099df582b7c4157dfed1ebe9ecf161efc8a3ab799630dc06977adafdffc7927",
    "ES_DE_RECEIPT_SHA256": GENERATED_INPUTS[6][2],
    "ES_DE_RUNNER_SHA256": GENERATED_INPUTS[1][2],
    "ES_DE_SYSTEMS_SHA256": GENERATED_INPUTS[0][2],
    "FLYCAST_CORE_SHA256": "1de0ebcad7de5906b2e03e3b7885254635399503969b5e1c8b21c8ef79c07eaf",
    "FRONTEND_UNIT_SHA256": "df3b6bdc3ba9b3ee65d18b9575c302cfa3aaff4fcc67fe6d12e825565c2ba05c",
    "REMOTE_GATEWAY_SHA256": "1b1ec52cec6d6e670d49789738d1a6c38d7f1b35c50bb24ba86ff1cd6203f9da",
    "REMOTE_INPUT_SHA256": GENERATED_INPUTS[3][2],
    "REMOTE_SUDOERS_SHA256": "2486b57b1312bea2477c4de629c2b5e60641f9016a3d3fb9c5be70e38b15e1fe",
    "SCREENSHOT_SHA256": GENERATED_INPUTS[2][2],
}
BASE.EXTRA_BUILD_INFO = {
    "consolidated_frontend": "ES-DE-3.4.1-r51",
    "consolidated_media_link_count": "6220",
    "consolidated_media_link_delta": "0",
    "consolidated_remote_input_actions": "16",
    "consolidated_system_count": "13",
    "dreamcast_menu": "hidden-known-panfrost-fault",
    "product_input_count": str(len(GENERATED_INPUTS)),
    "remote_input_hold_ms": "10",
    "remote_pairing": "required-after-image-write",
    "screenshot_process_guard": "anchored-command-line-one-plus-one",
    **{f"product_input_{name.replace('-', '_').replace('.', '_')}_sha256": digest
       for name, _size, digest in GENERATED_INPUTS},
    **{f"product_input_{name.replace('-', '_').replace('.', '_')}_size": str(size)
       for name, size, _digest in GENERATED_INPUTS},
}
BASE.CONSOLIDATED_RECEIPT_EXTRA_MARKERS = (
    "successor_base_artifact_id=debian13-p2-gaming-v0.15",
    "consolidated_frontend=ES-DE-3.4.1-r51",
    "consolidated_system_count=13",
    "consolidated_media_link_count=6220",
    "consolidated_media_link_delta=0",
    "consolidated_remote_input_actions=16",
    f"es_de_systems_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['ES_DE_SYSTEMS_SHA256']}",
    f"es_de_runner_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['ES_DE_RUNNER_SHA256']}",
    f"es_de_receipt_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['ES_DE_RECEIPT_SHA256']}",
    f"screenshot_helper_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['SCREENSHOT_SHA256']}",
    f"remote_input_sha256={BASE.EXTRA_BUILD_ENVIRONMENT['REMOTE_INPUT_SHA256']}",
    "remote_input_hold_ms=10",
    "screenshot_process_guard=anchored-command-line-one-plus-one",
    "dreamcast_menu=hidden-known-panfrost-fault",
    "remote_pairing=required-after-image-write",
)
BASE.SOURCE_PATHS = (
    README_RELATIVE,
    PRODUCT_DOC_RELATIVE,
    IMAGE_TOOL_RELATIVE,
    BUILDER_RELATIVE,
    TEST_RELATIVE,
    "mainline/gaming-remote-input/README.md",
    "mainline/gaming-remote-input/r46h-remote-input.c",
    "mainline/gaming-remote-screen/README.md",
    "mainline/gaming-remote-screen/r46h-screenshot",
    *BASE.SOURCE_PATHS,
)
BASE.APPLY_EVIDENCE = {
    "APPLY-DEBUGFS.txt", "CONSOLIDATED-RECEIPT", BASE.DEBUGFS_EVIDENCE_NAME,
    "DUMPE2FS.txt", "E2FSCK-REPAIR.txt", "E2FSCK.txt", "EXT4-VERIFIED.sha256",
    "GAMING-PAYLOAD-VERIFY.txt", "GAMING-RECEIPT", "NORMALIZE-SUPER.txt",
    "PRODUCT-VERIFY.txt", "SYSTEMD-VERIFY.txt", "TUNE2FS.txt", "UDEV-VERIFY.txt",
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
    BASE.APPLY_EVIDENCE | set(BASE.INDEPENDENT_EVIDENCE.values()) | {
        "BUILD-COMPLETE", "BUILD-INFO", "CONTAINER-APPLY.txt",
        "INDEPENDENT-VERIFY.txt", "INPUT-ARTIFACTS.sha256", "PRODUCT-INPUTS.sha256",
        "REPRODUCE.txt", "SHA256SUMS", "SOURCE-MANIFEST.json", BASE.IMAGE_NAME,
    }
)
BASE.STAGE_RE = re.compile(r"^\.r46h-debian13-p2-gaming-v0\.16\.tmp\.[A-Za-z0-9_]+$")

_validate_inputs = V15._validate_inputs
_write_build_metadata = V15._write_build_metadata
_validate_stage = V15._validate_stage


def replace_exact(data: bytes, old: bytes, new: bytes, count: int, label: str) -> bytes:
    if data.count(old) != count:
        raise BASE.BuildError(f"unexpected replacement count for {label}")
    return data.replace(old, new)


def extract_base_runtime(docker: str, destination: Path) -> None:
    paths = {
        "systems": "/etc/r46h/es-de-systems.xml",
        "runner": "/usr/local/sbin/r46h-es-de-ui",
        "firstboot": "/usr/libexec/r46h-firstboot",
        "smoke": "/usr/local/sbin/r46h-rootfs-smoke",
        "es-de-receipt": "/var/lib/r46h/gaming-es-de-v0.1-installed",
    }
    commands = ["set -eu", f"image=/input/{BASE.BASE_IMAGE.name}"]
    for name, path in paths.items():
        commands.append(f'debugfs -R \'dump -p "{path}" "/runtime/{name}"\' "$image" >/dev/null 2>&1')
    commands.append("chmod 0644 /runtime/*")
    result = subprocess.run(
        [docker, "--context", "desktop-linux", "run", "--rm", "--platform", "linux/arm64",
         "--network", "none", "--pull", "never",
         "--mount", f"type=bind,source={BASE.BASE_IMAGE.parent.resolve()},target=/input,readonly",
         "--mount", f"type=bind,source={destination.resolve()},target=/runtime",
         BASE.BASE_CONTAINER, "/bin/bash", "-c", "; ".join(commands)],
        check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if result.returncode != 0:
        raise BASE.BuildError(f"cannot extract v0.15 runtime inputs: {result.stdout.strip()}")


def compile_remote_input(docker: str, destination: Path) -> None:
    inspect = subprocess.run(
        [docker, "--context", "desktop-linux", "image", "inspect", "--format",
         "{{.Id}} {{.Architecture}} {{.Os}}", REMOTE_INPUT_BUILDER],
        check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if inspect.returncode != 0 or inspect.stdout.strip() != f"{REMOTE_INPUT_BUILDER} arm64 linux":
        raise BASE.BuildError("remote-input builder identity mismatch")
    result = subprocess.run(
        [docker, "--context", "desktop-linux", "run", "--rm", "--platform", "linux/arm64",
         "--network", "none", "--pull", "never", "--read-only",
         "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=32m",
         "--mount", f"type=bind,source={REMOTE_INPUT_SOURCE.parent.resolve()},target=/src,readonly",
         "--mount", f"type=bind,source={destination.parent.resolve()},target=/out",
         "--entrypoint", "/bin/sh", REMOTE_INPUT_BUILDER, "-c",
         "set -eu; gcc -std=c11 -O2 -fPIE -pie -D_FORTIFY_SOURCE=3 "
         "-DKEY_HOLD_MILLISECONDS=10 -fstack-protector-strong -Wall -Wextra -Werror "
         "-Wformat=2 -Wshadow -Wstrict-prototypes -Wl,-z,relro,-z,now "
         "-Wl,--build-id=none -ffile-prefix-map=/src=. -fdebug-prefix-map=/src=. "
         f"-o /out/.{destination.name}.tmp /src/r46h-remote-input.c; "
         f"strip --strip-unneeded /out/.{destination.name}.tmp; "
         f"chmod 0755 /out/.{destination.name}.tmp; mv /out/.{destination.name}.tmp /out/{destination.name}; "
         f"/out/{destination.name} --self-test; test \"$(/out/{destination.name} --version)\" = r46h-gaming-remote-input-v0.1"],
        check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if result.returncode != 0:
        raise BASE.BuildError(f"remote-input build failed: {result.stdout.strip()}")


def generate_runtime_inputs(base: Path, destination: Path) -> None:
    expected = BASE.EXTRA_BUILD_ENVIRONMENT
    base_files = {
        "systems": expected["BASE_ES_DE_SYSTEMS_SHA256"],
        "runner": expected["BASE_ES_DE_RUNNER_SHA256"],
        "firstboot": BASE.BASE_FIRSTBOOT_SHA256,
        "smoke": BASE.BASE_ROOTFS_SMOKE_SHA256,
        "es-de-receipt": expected["BASE_ES_DE_RECEIPT_SHA256"],
    }
    for name, digest in base_files.items():
        if BASE.sha256_file(base / name) != digest:
            raise BASE.BuildError(f"v0.15 runtime input mismatch: {name}")
    if BASE.sha256_file(SCREENSHOT_SOURCE) != "5f9aa5601df166b9769fcf7d31f8903622fcab97b645396b7efe798df814a7d3":
        raise BASE.BuildError("screenshot successor source mismatch")
    if BASE.sha256_file(DREAMCAST_FRAGMENT) != "fbe897e002a9f7430c2502b31e46567b923f8b44f21bc7434417bd52f17ebed9":
        raise BASE.BuildError("Dreamcast system fragment mismatch")

    systems = replace_exact((base / "systems").read_bytes(), DREAMCAST_FRAGMENT.read_bytes(), b"", 1, "Dreamcast system")
    runner = replace_exact((base / "runner").read_bytes(), BASE.BASE_FS_UUID.encode(), BASE.FS_UUID.encode(), 1, "runner UUID")
    runner = replace_exact(runner, expected["BASE_ES_DE_SYSTEMS_SHA256"].encode(), expected["ES_DE_SYSTEMS_SHA256"].encode(), 1, "runner systems hash")
    runner = replace_exact(runner, b"systems=14", b"systems=13", 1, "runner system count")
    screenshot = replace_exact(SCREENSHOT_SOURCE.read_bytes(), b"d3130007-46a4-4d56-9001-000000000007", BASE.FS_UUID.encode(), 1, "screenshot UUID")
    screenshot = replace_exact(screenshot, b"5b9edd8705d26ac2b58285baee9d2025354a0343936b5360313e664edd5bafa1", expected["ES_DE_RUNNER_SHA256"].encode(), 1, "screenshot runner hash")
    firstboot = replace_exact((base / "firstboot").read_bytes(), b"debian13-p2-gaming-v0.15", b"debian13-p2-gaming-v0.16", 2, "firstboot version")
    smoke = replace_exact((base / "smoke").read_bytes(), BASE.BASE_FS_UUID.encode(), BASE.FS_UUID.encode(), 1, "smoke UUID")
    smoke = replace_exact(smoke, b"debian13-p2-gaming-v0.15", b"debian13-p2-gaming-v0.16", 1, "smoke version")
    receipt = replace_exact((base / "es-de-receipt").read_bytes(), expected["BASE_ES_DE_SYSTEMS_SHA256"].encode(), expected["ES_DE_SYSTEMS_SHA256"].encode(), 1, "receipt systems hash")
    receipt = replace_exact(receipt, expected["BASE_ES_DE_RUNNER_SHA256"].encode(), expected["ES_DE_RUNNER_SHA256"].encode(), 1, "receipt runner hash")
    receipt = replace_exact(receipt, b"composition=offline-gamegear-successor-p2-v0.15", b"composition=offline-runtime-fix-successor-p2-v0.16", 1, "receipt composition")
    for name, data in (
        ("es-de-systems.v16.xml", systems), ("r46h-es-de-ui.v16", runner),
        ("r46h-screenshot.v16", screenshot), ("r46h-firstboot.v16", firstboot),
        ("r46h-rootfs-smoke.v16", smoke), ("es-de-receipt.v16", receipt),
    ):
        BASE.write_new(destination / name, data)


def validate_inputs(docker: str, extraction_root: Path) -> Path:
    payload = _validate_inputs(docker, extraction_root)
    destination = payload / "product-inputs"
    destination.mkdir(mode=0o700)
    base = destination / ".base"
    base.mkdir(mode=0o700)
    extract_base_runtime(docker, base)
    generate_runtime_inputs(base, destination)
    shutil.rmtree(base)
    compile_remote_input(docker, destination / "r46h-remote-input-10ms")
    if {path.name for path in destination.iterdir()} != {name for name, _size, _digest in GENERATED_INPUTS}:
        raise BASE.BuildError("unexpected v0.16 product input set")
    for name, size, digest in GENERATED_INPUTS:
        metadata = BASE.require_regular(destination / name, f"v0.16 product input {name}")
        if metadata.st_size != size or BASE.sha256_file(destination / name) != digest:
            raise BASE.BuildError(f"v0.16 product input mismatch: {name}")
    return payload


def product_input_receipt() -> bytes:
    return "".join(f"{digest}  {name}\n" for name, _size, digest in GENERATED_INPUTS).encode()


def write_build_metadata(*args: object, **kwargs: object) -> None:
    _write_build_metadata(*args, **kwargs)
    stage = args[0]
    assert isinstance(stage, Path)
    BASE.write_new(stage / "PRODUCT-INPUTS.sha256", product_input_receipt())


def validate_stage(stage: Path, expected_source_commit: str | None = None) -> str:
    image_sha256 = _validate_stage(stage, expected_source_commit)
    if (stage / "PRODUCT-INPUTS.sha256").read_bytes() != product_input_receipt():
        raise BASE.BuildError("v0.16 product input receipt mismatch")
    for name in ("PRODUCT-VERIFY.txt", "INDEPENDENT-PRODUCT-VERIFY.txt"):
        if "R46H_V16_PRODUCT_VERIFY_RESULT=pass" not in (stage / name).read_text(encoding="utf-8", errors="replace"):
            raise BASE.BuildError(f"v0.16 product verification marker missing: {name}")
    return image_sha256


BASE.validate_inputs = validate_inputs
BASE.write_build_metadata = write_build_metadata
BASE.validate_stage = validate_stage


if __name__ == "__main__":
    raise SystemExit(BASE.main())
