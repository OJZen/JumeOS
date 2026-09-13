#!/usr/bin/env python3
"""Safety and fixture tests for the R46H Hantro MPEG-2 decode probe."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "mainline/bringup-tests/r46h-hantro-mpeg2-decode-probe.c"
FIXTURE = REPO_ROOT / (
    "mainline/bringup-tests/fixtures/r46h-hantro-mpeg2-quadrants.m2v.b64"
)
RUNBOOK = REPO_ROOT / "mainline/bringup-tests/HANTRO-MPEG2-DECODE-PROBE.md"
BUILDER = "arkos4clone/r46h-kernel-builder:trixie-arm64"


class R46HHantroMpeg2DecodeProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")
        cls.fixture = base64.b64decode(FIXTURE.read_bytes().strip(), validate=True)

    def test_fixture_is_exact_single_intra_frame(self) -> None:
        self.assertEqual(len(self.fixture), 137)
        self.assertEqual(
            hashlib.sha256(self.fixture).hexdigest(),
            "8dd60e2ed78b0d364e6d071c3ea2d410be3da3d48a8ce086e7e1deacc20d8223",
        )
        self.assertEqual(self.fixture[:4], b"\x00\x00\x01\xb3")
        self.assertEqual(self.fixture[12:16], b"\x00\x00\x01\xb5")
        self.assertEqual(self.fixture[30:34], b"\x00\x00\x01\x00")
        self.assertEqual(self.fixture[38:42], b"\x00\x00\x01\xb5")
        self.assertEqual(
            hashlib.sha256(self.fixture[47:]).hexdigest(),
            "5c0718147bd0a0dd3e849c35bdd197b220ee03fea356d62f9af8684ba9fa1aac",
        )
        for code in range(1, 5):
            self.assertEqual(self.fixture.count(b"\x00\x00\x01" + bytes([code])), 1)

    def test_embedded_slices_match_fixture(self) -> None:
        block = re.search(
            r"static const uint8_t slice_data\[\] = \{(?P<body>.*?)\n\};",
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(block)
        values = bytes(
            int(value, 16) for value in re.findall(r"0x([0-9a-f]{2})", block["body"])
        )
        self.assertEqual(values, self.fixture[47:])
        self.assertEqual(len(values), 90)

    def test_exact_decoder_and_media_identity(self) -> None:
        for value in (
            "hantro-vpu",
            "rockchip,px30-vpu-dec",
            "platform:ff442000.video-codec",
            "V4L2_CAP_STREAMING",
            "V4L2_CAP_VIDEO_M2M_MPLANE",
            "MEDIA_IOC_DEVICE_INFO",
            "path_stat.st_rdev != fd_stat.st_rdev",
            "path_stat.st_ino != fd_stat.st_ino",
            "O_NOFOLLOW",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.source)
        self.assertGreaterEqual(self.source.count("validate_decoder_identity"), 3)
        self.assertGreaterEqual(self.source.count("validate_media_identity"), 3)

    def test_probe_uses_stateless_request_api(self) -> None:
        for value in (
            "V4L2_PIX_FMT_MPEG2_SLICE",
            "V4L2_PIX_FMT_NV12",
            "V4L2_BUF_CAP_SUPPORTS_REQUESTS",
            "V4L2_CID_STATELESS_MPEG2_SEQUENCE",
            "V4L2_CID_STATELESS_MPEG2_PICTURE",
            "V4L2_CID_STATELESS_MPEG2_QUANTISATION",
            "V4L2_CTRL_WHICH_REQUEST_VAL",
            "V4L2_BUF_FLAG_REQUEST_FD",
            "MEDIA_IOC_REQUEST_ALLOC",
            "MEDIA_REQUEST_IOC_QUEUE",
            "VIDIOC_STREAMON",
            "VIDIOC_DQBUF",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.source)

    def test_decoded_pattern_is_fully_validated(self) -> None:
        for value in (
            "row[x] != expected",
            "row[x] != 128U",
            "0x0833461a6e018325",
            "V4L2_BUF_FLAG_ERROR",
            "memset(capture_buffer.address, 0x5a",
            "R46H_HANTRO_MPEG2_DECODE result=pass",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.source)
        self.assertIn("#define LOGICAL_NV12_SIZE (WIDTH * HEIGHT * 3U / 2U)", self.source)

    def test_no_filesystem_or_system_mutation(self) -> None:
        forbidden = (
            r"\bfopen\s*\(",
            r"\bopenat\s*\(",
            r"\bwrite\s*\(",
            r"\bpwrite\w*\s*\(",
            r"\bfsync\s*\(",
            r"\bsystem\s*\(",
            r"\bmount\s*\(",
            r"\bmodprobe\b",
            r"O_CREAT",
            r"O_TRUNC",
        )
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, self.source))
        self.assertIn("writes no target file", self.runbook)
        self.assertIn("do not install it into p2", self.runbook)

    def test_cleanup_and_time_bounds_are_explicit(self) -> None:
        self.assertIn("VIDIOC_STREAMOFF", self.source)
        self.assertIn("munmap(mapped->address", self.source)
        self.assertIn("request.count = 0", self.source)
        self.assertIn("WAIT_TIMEOUT_MS 10000L", self.source)
        self.assertIn("SIGTERM", self.source)
        self.assertIn("cleanup_failed ? \"fail\" : \"pass\"", self.source)
        self.assertIn("timeout -s TERM -k 2s 20s", self.runbook)

    def test_runbook_pins_fixture_and_acceptance_boundaries(self) -> None:
        source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        self.assertEqual(
            source_hash,
            "6b4e6c310be73e302266b567df5e4669bf0035cc72f221d366c17a7a869f6aa9",
        )
        self.assertEqual(self.runbook.count(source_hash), 1)
        for digest in (
            "8dd60e2ed78b0d364e6d071c3ea2d410be3da3d48a8ce086e7e1deacc20d8223",
            "5c0718147bd0a0dd3e849c35bdd197b220ee03fea356d62f9af8684ba9fa1aac",
            "7ed819ce0022734308195d983899a72cc5cbbc40bf849b358dab4b33e49d6fd0",
            "40ba4aa960ac873654b9c8641a889ab00157eb2e029d5bb1164fe2196059b13e",
            "cc6783b41d770ddc3e9ec0bc0098eac40ba19f4c4c8dc92999244604bff2be88",
        ):
            with self.subTest(digest=digest):
                self.assertIn(digest, self.runbook)
        self.assertIn("one MPEG-2 intra frame", self.runbook)
        self.assertIn("does not prove H.264 or VP8", self.runbook)
        self.assertIn("does not prove sustained decoding", self.runbook)
        self.assertIn("R46H_HANTRO_ACCEPTANCE result=pass cleanup=pass", self.runbook)

    @unittest.skipUnless(
        os.environ.get("R46H_RUN_HANTRO_DECODE_SOFTWARE") == "1",
        "set R46H_RUN_HANTRO_DECODE_SOFTWARE=1 for the FFmpeg fixture gate",
    )
    def test_fixture_software_decode_matches_expected_nv12(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        self.assertIsNotNone(ffmpeg)
        cache_root = REPO_ROOT / "mainline/out/.cache"
        with tempfile.TemporaryDirectory(
            prefix="r46h-hantro-decode-software.", dir=cache_root
        ) as temporary:
            source = Path(temporary) / "frame.m2v"
            output = Path(temporary) / "frame.nv12"
            source.write_bytes(self.fixture)
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(source),
                    "-frames:v",
                    "1",
                    "-pix_fmt",
                    "nv12",
                    "-f",
                    "rawvideo",
                    "-y",
                    str(output),
                ],
                check=True,
            )
            decoded = output.read_bytes()
            self.assertEqual(len(decoded), 6144)
            self.assertEqual(
                hashlib.sha256(decoded).hexdigest(),
                "7ed819ce0022734308195d983899a72cc5cbbc40bf849b358dab4b33e49d6fd0",
            )

    @unittest.skipUnless(
        os.environ.get("R46H_RUN_HANTRO_DECODE_BUILD") == "1",
        "set R46H_RUN_HANTRO_DECODE_BUILD=1 for the ARM64 Docker compile gate",
    )
    def test_arm64_probe_builds_with_warnings_as_errors(self) -> None:
        cache_root = REPO_ROOT / "mainline/out/.cache"
        with tempfile.TemporaryDirectory(
            prefix="r46h-hantro-decode-build.", dir=cache_root
        ) as temporary:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--user",
                    f"{os.getuid()}:{os.getgid()}",
                    "-v",
                    f"{SOURCE.parent}:/src:ro",
                    "-v",
                    f"{temporary}:/out",
                    "-w",
                    "/out",
                    "--entrypoint",
                    "/bin/bash",
                    BUILDER,
                    "-lc",
                    "gcc -std=c11 -O2 -Wall -Wextra -Werror "
                    "-o r46h-hantro-mpeg2-decode-probe "
                    "/src/r46h-hantro-mpeg2-decode-probe.c",
                ],
                check=True,
            )
            self.assertTrue(
                (Path(temporary) / "r46h-hantro-mpeg2-decode-probe").is_file()
            )


if __name__ == "__main__":
    unittest.main()
