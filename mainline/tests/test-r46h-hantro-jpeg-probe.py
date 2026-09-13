#!/usr/bin/env python3
"""Safety and acceptance tests for the R46H Hantro JPEG data-path probe."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "mainline/bringup-tests/r46h-hantro-jpeg-probe.c"
RUNBOOK = REPO_ROOT / "mainline/bringup-tests/HANTRO-JPEG-PROBE.md"
BUILDER = "arkos4clone/r46h-kernel-builder:trixie-arm64"


class R46HHantroJpegProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")

    def test_exact_encoder_identity_and_fd_binding(self) -> None:
        for value in (
            "hantro-vpu",
            "rockchip,px30-vpu-enc",
            "platform:ff442000.video-codec",
            "V4L2_CAP_STREAMING",
            "V4L2_CAP_VIDEO_M2M_MPLANE",
            "VIDIOC_QUERYCAP",
            "path_stat.st_rdev != fd_stat.st_rdev",
            "path_stat.st_ino != fd_stat.st_ino",
            "O_NOFOLLOW",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.source)
        self.assertIn("lstat(path, &path_stat)", self.source)
        self.assertIn("fstat(fd, &fd_stat)", self.source)

    def test_probe_exercises_one_real_mem2mem_encode(self) -> None:
        for value in (
            "V4L2_PIX_FMT_YUV420M",
            "V4L2_PIX_FMT_JPEG",
            "VIDIOC_REQBUFS",
            "VIDIOC_QUERYBUF",
            "VIDIOC_QBUF",
            "VIDIOC_STREAMON",
            "VIDIOC_DQBUF",
            "mmap(NULL",
            "R46H_HANTRO_JPEG result=pass",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.source)
        self.assertIn("#define WIDTH 96U", self.source)
        self.assertIn("#define HEIGHT 32U", self.source)
        self.assertIn("fill_yuv420m", self.source)
        self.assertNotIn("SKIP_TOOLING", self.source)

    def test_jpeg_output_is_structurally_validated(self) -> None:
        self.assertIn('memcmp(bytes + 6, "JFIF\\0", 5)', self.source)
        self.assertIn("marker == 0xc0U", self.source)
        self.assertIn("bytes[length - 1U] != 0xd9U", self.source)
        self.assertIn("capture_buffer.flags & V4L2_BUF_FLAG_ERROR", self.source)
        self.assertIn("fnv1a64", self.source)
        self.assertIn("R46H_HANTRO_JPEG_BASE64_BEGIN", self.source)
        self.assertIn("R46H_HANTRO_JPEG_BASE64_END", self.source)

    def test_default_probe_has_no_file_or_system_mutation(self) -> None:
        forbidden = (
            r"\bopenat\s*\(",
            r"\bwrite\s*\(",
            r"\bpwrite\w*\s*\(",
            r"\bfsync\s*\(",
            r"\bsystem\s*\(",
            r"\bmount\s*\(",
            r"\bmodprobe\b",
            r"O_WRONLY",
            r"O_CREAT",
        )
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, self.source))
        self.assertIn("The default mode writes no file", self.runbook)
        self.assertIn("do not install it into p2", self.runbook)

    def test_cleanup_and_time_bounds_are_explicit(self) -> None:
        self.assertEqual(self.source.count("VIDIOC_STREAMOFF"), 2)
        self.assertIn("munmap(mapped->address[i]", self.source)
        self.assertIn("elapsed_ms >= 10000L", self.source)
        self.assertIn('cleanup_failed ? "fail" : "pass"', self.source)
        self.assertIn("timeout -s TERM -k 2s 20s", self.runbook)
        self.assertIn("cleanup=pass", self.runbook)

    def test_runbook_pins_source_binary_and_decoded_jpeg(self) -> None:
        source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        self.assertEqual(
            source_hash,
            "a7cef1df4ee01bbf723d971293a710521147c75c4c74c8716ca8b79ffbb914a0",
        )
        self.assertEqual(self.runbook.count(source_hash), 1)
        for digest in (
            "dfa0a9c0b4cda9855c8ef58b1dfdc7a12b5546575cee0400023c58f763515b37",
            "d075cdac6b5ad5de736aa6fdf4d1d2f1fc15605ff7902856f4df8a1a0468683c",
            "f5816a87dc8e24bae332717ac42a2c44152734bd1d2972dd3165c0e0fd32bfd5",
            "516560bdeaf68487777040714bf7bda95a7dd6b427918870988a325257b48f28",
        ):
            with self.subTest(digest=digest):
                self.assertIn(digest, self.runbook)
        self.assertIn("does not close the decoder", self.runbook)
        self.assertIn("one MPEG-2 intra-frame path later passed", self.runbook)
        self.assertIn("H.264,\nVP8 and sustained decode remain open", self.runbook)
        self.assertIn("R46H_HANTRO_FINAL_EXIT status=0", self.runbook)
        self.assertIn("final target-tmpfs cleanup with zero residue", self.runbook)

    @unittest.skipUnless(
        os.environ.get("R46H_RUN_HANTRO_PROBE_BUILD") == "1",
        "set R46H_RUN_HANTRO_PROBE_BUILD=1 for the ARM64 Docker compile gate",
    )
    def test_arm64_probe_builds_with_warnings_as_errors(self) -> None:
        output = REPO_ROOT / "mainline/out/.cache/r46h-hantro-probe-test"
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        try:
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
                    f"{output}:/out",
                    "-w",
                    "/out",
                    "--entrypoint",
                    "/bin/bash",
                    BUILDER,
                    "-lc",
                    "gcc -std=c11 -O2 -Wall -Wextra -Werror "
                    "-o r46h-hantro-jpeg-probe /src/r46h-hantro-jpeg-probe.c",
                ],
                check=True,
            )
            self.assertTrue((output / "r46h-hantro-jpeg-probe").is_file())
        finally:
            for child in output.iterdir():
                child.unlink()
            output.rmdir()


if __name__ == "__main__":
    unittest.main()
