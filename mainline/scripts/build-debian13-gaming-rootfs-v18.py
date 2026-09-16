#!/usr/bin/env python3
"""Build the R46H gaming p2 v0.18 local-network-policy successor."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import sys


REPO = Path(__file__).resolve().parents[2]
V17_BUILDER_PATH = REPO / "mainline/scripts/build-debian13-gaming-rootfs-v17.py"
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v17_base", V17_BUILDER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the Debian gaming v0.17 builder")
V17 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = V17
SPEC.loader.exec_module(V17)
BASE = V17.BASE


README_RELATIVE = "mainline/rootfs-debian13-gaming-v18/README.md"
IMAGE_TOOL_RELATIVE = "mainline/rootfs-debian13-gaming-v18/image-in-container.sh"
BUILDER_RELATIVE = "mainline/scripts/build-debian13-gaming-rootfs-v18.py"
TEST_RELATIVE = "mainline/tests/test-debian13-gaming-rootfs-v18.py"
RULE_RELATIVE = "mainline/gaming-shell/49-r46h-network.rules"
PACKAGE_ROOT = BASE.OUTPUT_ROOT / ".cache/r46h-polkit-v18/debs"
RULE = REPO / RULE_RELATIVE
RULE_SHA256 = "842466c1aafc51d187abb1ec3204d7c34579d56149249947619c8967ecccc87e"

PACKAGES = (
    ("libduktape207", "2.7.0-2+b2", "arm64", "libduktape207_2.7.0-2+b2_arm64.deb", 126_528,
     "9dcf4d316a8ece7277d21bbdd26b75a5d7d829faf3c7cfd861e30ba89d385516"),
    ("libpolkit-agent-1-0", "126-2", "arm64", "libpolkit-agent-1-0_126-2_arm64.deb", 25_408,
     "34bf6b2c8afd65061c95157eb8f5d605e1c79f361df3b036bdfa8a40b69edcf5"),
    ("libpolkit-gobject-1-0", "126-2", "arm64", "libpolkit-gobject-1-0_126-2_arm64.deb", 46_328,
     "e8c2e996ad45fef730c40a3b0de34ec878307d4347e63e19cd15e59bd9ac3dcc"),
    ("polkitd", "126-2", "arm64", "polkitd_126-2_arm64.deb", 119_368,
     "6db47b46bb238687f63fc8dea0369377a471ddcd0b0fdcc72dba9ca2818ac772"),
    ("sgml-base", "1.31+nmu1", "all", "sgml-base_1.31+nmu1_all.deb", 10_868,
     "a355b832d9f0f4dc9eca1a661080db5dc118e6c435f107a5c4dd201d7af59ba8"),
    ("xml-core", "0.19", "all", "xml-core_0.19_all.deb", 20_088,
     "079ec5e10b1c49aa23a6c53ae8e55e33aec121d1c87a131d2172bdabc3f4030e"),
)
PACKAGE_MANIFEST = "".join(
    f"{package}\t{version}\t{architecture}\t{filename}\t{digest}\n"
    for package, version, architecture, filename, _size, digest in PACKAGES
).encode()
PACKAGE_MANIFEST_SHA256 = BASE.sha256_bytes(PACKAGE_MANIFEST)

GENERATED_INPUTS = (
    ("r46h-es-de-ui.v18", 10_026, "d1f6388ede65a93b30ee42151609dff6bd0b3476eec036f91485300311591cce"),
    ("r46h-screenshot.v18", 11_371, "8f926f66233e42a91b0561e9759bd66f091bcd8562eb489bd5ac8623d557a666"),
    ("r46h-firstboot.v18", 837, "3f5c36267f619c424fa25c08f9b46de7c77163ea84e4e4e0f863d3fbc0ec0a82"),
    ("r46h-rootfs-smoke.v18", 8_295, "877abf1e8feaaa80eb545a8292117cf4df9f237b9c24db7d72f459d310c03caa"),
    ("es-de-receipt.v18", 2_594, "064317c21829ba49867819775cac71d7e815bd66d543dfe23beed3e560a37724"),
)

_base_validate_inputs = V17._validate_inputs
_write_build_metadata = V17._write_build_metadata
_validate_stage = V17._validate_stage
_v17_receipt_markers = BASE.CONSOLIDATED_RECEIPT_EXTRA_MARKERS

BASE.CACHE_ROOT = BASE.OUTPUT_ROOT / ".cache/r46h-debian13-gaming-rootfs-v18"
BASE.OUTPUT_NAME = "r46h-debian13-p2-gaming-v0.18"
BASE.ARTIFACT_ID = "debian13-p2-gaming-v0.18"
BASE.IMAGE_NAME = f"{BASE.OUTPUT_NAME}.ext4"
BASE.OUTPUT_DIR = BASE.OUTPUT_ROOT / BASE.OUTPUT_NAME
BASE.BASE_FS_UUID = "d3130017-46a4-4d56-9001-000000000017"
BASE.BASE_FS_LABEL = "R46H_GAMING_V17"
BASE.FS_UUID = "d3130018-46a4-4d56-9001-000000000018"
BASE.FS_LABEL = "R46H_GAMING_V18"
BASE.SOURCE_DATE_EPOCH = "1789516800"
BASE.BASE_IMAGE = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.17/r46h-debian13-p2-gaming-v0.17.ext4"
BASE.BASE_IMAGE_SHA256 = "efccaf9b1d6b48624427f96f0d995c0143cb50e3447f31506ef6553973538897"
BASE.BASE_BUILD_INFO = BASE.OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.17/BUILD-INFO"
BASE.BASE_BUILD_INFO_SHA256 = "45c7c732d36b8fb6ee5b33232ae69041e6159b285b667ab7eba2a81f34a9947e"
BASE.BASE_CONSOLIDATED_RECEIPT_SHA256 = "67ed46759d1345fd5189e503376a63ce2d0f8082d705ea8059198858f0fcd1c2"
BASE.BASE_FIRSTBOOT_SHA256 = "17382bfb2616a39006c91aa7c5cfec8acd62b6f49d8bed74b5088b6e5ed619da"
BASE.FINAL_FIRSTBOOT_SHA256 = GENERATED_INPUTS[2][2]
BASE.BASE_ROOTFS_SMOKE_SHA256 = "9c07a3dc94ea9a907c0c597a802c7c4a6e19f60cce4e6627385891ae5eb75a22"
BASE.FINAL_ROOTFS_SMOKE_SHA256 = GENERATED_INPUTS[3][2]
BASE.VERSION_TEXT = "v0.18"
BASE.VERSION_TOKEN = "V18"
BASE.IMAGE_TOOL_RELATIVE = IMAGE_TOOL_RELATIVE
BASE.BASE_IMAGE_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.17.ext4"
BASE.BASE_BUILD_INFO_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.17.BUILD-INFO"
BASE.DEBUGFS_EVIDENCE_NAME = "DEBUGFS-V18.txt"
BASE.INDEPENDENT_DEBUGFS_EVIDENCE_NAME = "INDEPENDENT-DEBUGFS-V18.txt"
BASE.ARTIFACT_STATUS = "host-only-no-media-operation-performed"
BASE.SUCCESSOR_METHOD = "offline-ext4-repack-local-debs"
BASE.CONTAINER_PRIVILEGED = True

BASE.EXTRA_BUILD_ENVIRONMENT = {
    **BASE.EXTRA_BUILD_ENVIRONMENT,
    "ES_DE_RECEIPT_SHA256": GENERATED_INPUTS[4][2],
    "ES_DE_RUNNER_SHA256": GENERATED_INPUTS[0][2],
    "NETWORK_RULE_SHA256": RULE_SHA256,
    "POLKIT_PACKAGE_MANIFEST_SHA256": PACKAGE_MANIFEST_SHA256,
    "SCREENSHOT_SHA256": GENERATED_INPUTS[1][2],
}
BASE.EXTRA_BUILD_INFO = {
    **BASE.EXTRA_BUILD_INFO,
    "network_policy_actions": "3",
    "network_policy_packages_sha256": PACKAGE_MANIFEST_SHA256,
    "network_policy_rule_sha256": RULE_SHA256,
    "network_policy_scope": "ark-only",
    "product_input_count": str(len(GENERATED_INPUTS) + len(PACKAGES) + 2),
}
_replaced_receipt_prefixes = (
    "successor_base_artifact_id=", "es_de_runner_sha256=", "es_de_receipt_sha256=",
    "screenshot_helper_sha256=",
)
BASE.CONSOLIDATED_RECEIPT_EXTRA_MARKERS = (
    *(line for line in _v17_receipt_markers if not line.startswith(_replaced_receipt_prefixes)),
    "successor_base_artifact_id=debian13-p2-gaming-v0.17",
    f"es_de_runner_sha256={GENERATED_INPUTS[0][2]}",
    f"es_de_receipt_sha256={GENERATED_INPUTS[4][2]}",
    f"screenshot_helper_sha256={GENERATED_INPUTS[1][2]}",
    f"network_policy_packages_sha256={PACKAGE_MANIFEST_SHA256}",
    f"network_policy_rule_sha256={RULE_SHA256}",
    "network_policy_scope=ark-only-three-actions",
    "polkitd_version=126-2",
)
BASE.SOURCE_PATHS = (
    README_RELATIVE, IMAGE_TOOL_RELATIVE, BUILDER_RELATIVE, TEST_RELATIVE, RULE_RELATIVE,
    *BASE.SOURCE_PATHS,
)
BASE.APPLY_EVIDENCE = {
    "CONSOLIDATED-RECEIPT", BASE.DEBUGFS_EVIDENCE_NAME, "DUMPE2FS.txt",
    "E2FSCK.txt", "EXT4-VERIFIED.sha256", "GAMING-RECEIPT",
    "PACKAGE-VERIFY.txt", "PRODUCT-VERIFY.txt", "SYSTEMD-VERIFY.txt", "UDEV-VERIFY.txt",
}
BASE.INDEPENDENT_EVIDENCE = {
    BASE.DEBUGFS_EVIDENCE_NAME: BASE.INDEPENDENT_DEBUGFS_EVIDENCE_NAME,
    "E2FSCK.txt": "INDEPENDENT-E2FSCK.txt",
    "EXT4-VERIFIED.sha256": "INDEPENDENT-EXT4-VERIFIED.sha256",
    "PACKAGE-VERIFY.txt": "INDEPENDENT-PACKAGE-VERIFY.txt",
    "PRODUCT-VERIFY.txt": "INDEPENDENT-PRODUCT-VERIFY.txt",
    "SYSTEMD-VERIFY.txt": "INDEPENDENT-SYSTEMD-VERIFY.txt",
    "UDEV-VERIFY.txt": "INDEPENDENT-UDEV-VERIFY.txt",
}
BASE.REQUIRED_STAGE_FILES = (
    BASE.APPLY_EVIDENCE | set(BASE.INDEPENDENT_EVIDENCE.values()) | {
        "BUILD-COMPLETE", "BUILD-INFO", "CONTAINER-APPLY.txt", "INDEPENDENT-VERIFY.txt",
        "INPUT-ARTIFACTS.sha256", "PRODUCT-INPUTS.sha256", "REPRODUCE.txt", "SHA256SUMS",
        "SOURCE-MANIFEST.json", BASE.IMAGE_NAME,
    }
)
BASE.STAGE_RE = re.compile(r"^\.r46h-debian13-p2-gaming-v0\.18\.tmp\.[A-Za-z0-9_]+$")


def replace_exact(data: bytes, old: bytes, new: bytes, count: int, label: str) -> bytes:
    if data.count(old) != count:
        raise BASE.BuildError(f"unexpected replacement count for {label}")
    return data.replace(old, new)


def generate_runtime_inputs(v17_inputs: dict[str, bytes], destination: Path) -> None:
    old_uuid = BASE.BASE_FS_UUID.encode()
    new_uuid = BASE.FS_UUID.encode()
    old_runner = V17.GENERATED_INPUTS[1][2].encode()
    new_runner = GENERATED_INPUTS[0][2].encode()
    runner = replace_exact(v17_inputs["r46h-es-de-ui.v17"], old_uuid, new_uuid, 1, "runner UUID")
    screenshot = replace_exact(v17_inputs["r46h-screenshot.v17"], old_uuid, new_uuid, 1, "screenshot UUID")
    screenshot = replace_exact(screenshot, old_runner, new_runner, 1, "screenshot runner hash")
    firstboot = replace_exact(v17_inputs["r46h-firstboot.v17"], b"debian13-p2-gaming-v0.17", b"debian13-p2-gaming-v0.18", 2, "firstboot version")
    smoke = replace_exact(v17_inputs["r46h-rootfs-smoke.v17"], old_uuid, new_uuid, 1, "smoke UUID")
    smoke = replace_exact(smoke, b"debian13-p2-gaming-v0.17", b"debian13-p2-gaming-v0.18", 1, "smoke version")
    receipt = replace_exact(v17_inputs["es-de-receipt.v17"], old_runner, new_runner, 1, "receipt runner hash")
    receipt = replace_exact(receipt, b"offline-exclusive-systems-successor-p2-v0.17", b"offline-network-policy-successor-p2-v0.18", 1, "receipt composition")
    for (name, _size, _digest), data in zip(
        GENERATED_INPUTS, (runner, screenshot, firstboot, smoke, receipt), strict=True
    ):
        BASE.write_new(destination / name, data)


def extract_base_runtime(docker: str, destination: Path) -> None:
    paths = {
        "r46h-es-de-ui.v17": "/usr/local/sbin/r46h-es-de-ui",
        "r46h-screenshot.v17": "/usr/local/bin/r46h-screenshot",
        "r46h-firstboot.v17": "/usr/libexec/r46h-firstboot",
        "r46h-rootfs-smoke.v17": "/usr/local/sbin/r46h-rootfs-smoke",
        "es-de-receipt.v17": "/var/lib/r46h/gaming-es-de-v0.1-installed",
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
        raise BASE.BuildError(f"cannot extract v0.17 runtime inputs: {result.stdout.strip()}")
    expected = {name: (size, digest) for name, size, digest in V17.GENERATED_INPUTS}
    for name in paths:
        size, digest = expected[name]
        metadata = BASE.require_regular(destination / name, f"v0.17 runtime input {name}")
        if metadata.st_size != size or BASE.sha256_file(destination / name) != digest:
            raise BASE.BuildError(f"v0.17 runtime input mismatch: {name}")


def validate_deb_metadata(docker: str, inputs: Path) -> None:
    result = subprocess.run(
        [docker, "--context", "desktop-linux", "run", "--rm", "--platform", "linux/arm64",
         "--network", "none", "--pull", "never", "--read-only",
         "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=8m",
         "--mount", f"type=bind,source={inputs.resolve()},target=/inputs,readonly",
         BASE.BASE_CONTAINER, "/bin/bash", "-ec",
         "while IFS=$'\\t' read -r p v a f h; do "
         "test \"$(sha256sum /inputs/$f | awk '{print $1}')\" = \"$h\"; "
         "test \"$(dpkg-deb -f /inputs/$f Package)\" = \"$p\"; "
         "test \"$(dpkg-deb -f /inputs/$f Version)\" = \"$v\"; "
         "test \"$(dpkg-deb -f /inputs/$f Architecture)\" = \"$a\"; "
         "done < /inputs/POLKIT-PACKAGES.tsv"],
        check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if result.returncode != 0:
        raise BASE.BuildError(f"polkit package metadata mismatch: {result.stdout.strip()}")


def validate_inputs(docker: str, extraction_root: Path) -> Path:
    payload = _base_validate_inputs(docker, extraction_root)
    destination = payload / "product-inputs"
    destination.mkdir(mode=0o700)
    runtime = extraction_root / "v17-runtime"
    runtime.mkdir(mode=0o700)
    extract_base_runtime(docker, runtime)
    v17_inputs = {path.name: path.read_bytes() for path in runtime.iterdir()}
    shutil.rmtree(runtime)
    generate_runtime_inputs(v17_inputs, destination)
    for name, size, digest in GENERATED_INPUTS:
        metadata = BASE.require_regular(destination / name, f"v0.18 product input {name}")
        if metadata.st_size != size or BASE.sha256_file(destination / name) != digest:
            raise BASE.BuildError(f"v0.18 product input mismatch: {name}")
    for _package, _version, _architecture, filename, size, digest in PACKAGES:
        source = PACKAGE_ROOT / filename
        metadata = BASE.require_regular(source, f"polkit package {filename}")
        if metadata.st_size != size or BASE.sha256_file(source) != digest:
            raise BASE.BuildError(f"polkit package mismatch: {filename}")
        shutil.copyfile(source, destination / filename)
    if BASE.sha256_file(RULE) != RULE_SHA256:
        raise BASE.BuildError("network policy rule mismatch")
    shutil.copyfile(RULE, destination / RULE.name)
    BASE.write_new(destination / "POLKIT-PACKAGES.tsv", PACKAGE_MANIFEST)
    validate_deb_metadata(docker, destination)
    return payload


def product_input_receipt() -> bytes:
    inputs = [*GENERATED_INPUTS]
    inputs.extend((filename, size, digest) for _p, _v, _a, filename, size, digest in PACKAGES)
    inputs.extend(((RULE.name, RULE.stat().st_size, RULE_SHA256),
                   ("POLKIT-PACKAGES.tsv", len(PACKAGE_MANIFEST), PACKAGE_MANIFEST_SHA256)))
    return "".join(f"{digest}  {name}\n" for name, _size, digest in sorted(inputs)).encode()


def write_build_metadata(*args: object, **kwargs: object) -> None:
    _write_build_metadata(*args, **kwargs)
    stage = args[0]
    assert isinstance(stage, Path)
    BASE.write_new(stage / "PRODUCT-INPUTS.sha256", product_input_receipt())


def validate_stage(stage: Path, expected_source_commit: str | None = None) -> str:
    image_sha256 = _validate_stage(stage, expected_source_commit)
    if (stage / "PRODUCT-INPUTS.sha256").read_bytes() != product_input_receipt():
        raise BASE.BuildError("v0.18 product input receipt mismatch")
    markers = {
        "PACKAGE-VERIFY.txt": "R46H_V18_PACKAGE_VERIFY_RESULT=pass",
        "INDEPENDENT-PACKAGE-VERIFY.txt": "R46H_V18_PACKAGE_VERIFY_RESULT=pass",
        "PRODUCT-VERIFY.txt": "R46H_V18_PRODUCT_VERIFY_RESULT=pass",
        "INDEPENDENT-PRODUCT-VERIFY.txt": "R46H_V18_PRODUCT_VERIFY_RESULT=pass",
    }
    for name, marker in markers.items():
        if marker not in (stage / name).read_text(encoding="utf-8", errors="replace"):
            raise BASE.BuildError(f"v0.18 verification marker missing: {name}")
    return image_sha256


BASE.validate_inputs = validate_inputs
BASE.write_build_metadata = write_build_metadata
BASE.validate_stage = validate_stage


if __name__ == "__main__":
    raise SystemExit(BASE.main())
