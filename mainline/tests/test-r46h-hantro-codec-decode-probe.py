#!/usr/bin/env python3
"""Safety and fixture tests for the R46H H.264/VP8 decode probe."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "mainline/bringup-tests/r46h-hantro-codec-decode-probe.c"
H264_FIXTURE = REPO_ROOT / (
    "mainline/bringup-tests/fixtures/r46h-hantro-quadrants.h264.b64"
)
VP8_FIXTURE = REPO_ROOT / (
    "mainline/bringup-tests/fixtures/r46h-hantro-quadrants.ivf.b64"
)
H264_REFERENCE_FIXTURE = REPO_ROOT / (
    "mainline/bringup-tests/fixtures/r46h-hantro-quadrants-idr-p.h264.b64"
)
VP8_REFERENCE_FIXTURE = REPO_ROOT / (
    "mainline/bringup-tests/fixtures/r46h-hantro-quadrants-key-inter.ivf.b64"
)
RUNBOOK = REPO_ROOT / "mainline/bringup-tests/HANTRO-CODEC-DECODE-PROBE.md"
BUILDER = "arkos4clone/r46h-kernel-builder:trixie-arm64"
NV12_SHA256 = "7ed819ce0022734308195d983899a72cc5cbbc40bf849b358dab4b33e49d6fd0"


def extract_c_byte_array(source: str, name: str) -> bytes:
    block = re.search(
        rf"static const uint8_t {re.escape(name)}\[\] = \{{(?P<body>.*?)\n\}};",
        source,
        re.DOTALL,
    )
    if block is None:
        raise AssertionError(f"missing C byte array: {name}")
    return bytes(
        int(value, 16) for value in re.findall(r"0x([0-9a-fA-F]{2})", block["body"])
    )


def extract_c_hex_string(source: str, name: str) -> bytes:
    block = re.search(
        rf"static const char {re.escape(name)}\[\] =(?P<body>.*?);",
        source,
        re.DOTALL,
    )
    if block is None:
        raise AssertionError(f"missing C hex string: {name}")
    value = "".join(re.findall(r'"([0-9a-fA-F]+)"', block["body"]))
    return bytes.fromhex(value)


class R46HHantroCodecDecodeProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")
        cls.h264 = base64.b64decode(H264_FIXTURE.read_bytes().strip(), validate=True)
        cls.ivf = base64.b64decode(VP8_FIXTURE.read_bytes().strip(), validate=True)
        cls.h264_reference = base64.b64decode(
            H264_REFERENCE_FIXTURE.read_bytes().strip(), validate=True
        )
        cls.vp8_reference = base64.b64decode(
            VP8_REFERENCE_FIXTURE.read_bytes().strip(), validate=True
        )

    def test_h264_fixture_and_embedded_idr_are_exact(self) -> None:
        self.assertEqual(len(self.h264), 70)
        self.assertEqual(
            hashlib.sha256(self.h264).hexdigest(),
            "c03078b67bc1de5eed12f4ba8a8932560a455a21e24c0f09c340728057673752",
        )
        self.assertEqual(self.h264[:5], b"\x00\x00\x00\x01\x67")
        self.assertEqual(self.h264[24:29], b"\x00\x00\x00\x01\x68")
        self.assertEqual(self.h264[33:37], b"\x00\x00\x01\x65")
        self.assertEqual([self.h264[4] & 0x1F, self.h264[28] & 0x1F,
                          self.h264[36] & 0x1F], [7, 8, 5])
        self.assertEqual(self.h264.count(b"\x00\x00\x01"), 3)
        slice_data = self.h264[33:]
        self.assertEqual(len(slice_data), 37)
        self.assertEqual(
            hashlib.sha256(slice_data).hexdigest(),
            "ba6606496410c0f1853ab07df590efb17012bdeb850e233e82b673459241d2eb",
        )
        self.assertEqual(extract_c_byte_array(self.source, "h264_slice_data"), slice_data)

    def test_vp8_fixture_and_embedded_keyframe_are_exact(self) -> None:
        self.assertEqual(len(self.ivf), 89)
        self.assertEqual(
            hashlib.sha256(self.ivf).hexdigest(),
            "77940c19ceed0dc95e9dc63a5580c8112454d6b2453d3a2b4d04f76732fb81ff",
        )
        self.assertEqual(self.ivf[:4], b"DKIF")
        self.assertEqual(self.ivf[8:12], b"VP80")
        self.assertEqual(struct.unpack_from("<HH", self.ivf, 12), (64, 64))
        self.assertEqual(struct.unpack_from("<I", self.ivf, 24)[0], 1)
        self.assertEqual(struct.unpack_from("<I", self.ivf, 32)[0], 45)
        frame = self.ivf[44:]
        self.assertEqual(len(frame), 45)
        self.assertEqual(
            hashlib.sha256(frame).hexdigest(),
            "29a8523996219507c3e26c0b9b40d21fb83300d2a0b684dbe98bd4bd15e0f65f",
        )
        frame_tag = int.from_bytes(frame[:3], "little")
        self.assertEqual(frame_tag & 1, 0)
        self.assertEqual((frame_tag >> 4) & 1, 1)
        self.assertEqual(frame_tag >> 5, 24)
        self.assertEqual(frame[3:6], b"\x9d\x01\x2a")
        self.assertEqual(int.from_bytes(frame[6:8], "little") & 0x3FFF, 64)
        self.assertEqual(int.from_bytes(frame[8:10], "little") & 0x3FFF, 64)
        self.assertEqual(extract_c_byte_array(self.source, "vp8_frame_data"), frame)

    def test_h264_idr_p_fixture_and_embedded_slices_are_exact(self) -> None:
        self.assertEqual(len(self.h264_reference), 646)
        self.assertEqual(
            hashlib.sha256(self.h264_reference).hexdigest(),
            "a3451b0fe905a3c5ea8143b91cb3d05526fa3f5d16f75f6cf4db26355dd791b6",
        )
        idr = self.h264_reference[599:637]
        p_frame = self.h264_reference[637:]
        self.assertEqual((len(idr), len(p_frame)), (38, 9))
        self.assertEqual(idr[:4], b"\x00\x00\x01\x65")
        self.assertEqual(p_frame[:5], b"\x00\x00\x00\x01\x41")
        self.assertEqual(
            hashlib.sha256(idr).hexdigest(),
            "155b2dca06f96aec0bc76df800466bcf72c39083048bddc8fd5060f0187a8171",
        )
        self.assertEqual(
            hashlib.sha256(p_frame).hexdigest(),
            "a8ffb22d06b9be8995bc09817a0650343a162b35ab027a537210d953c55a4719",
        )
        self.assertEqual(
            extract_c_byte_array(self.source, "h264_reference_idr_data"), idr
        )
        self.assertEqual(
            extract_c_byte_array(self.source, "h264_reference_p_data"), p_frame
        )

    def test_vp8_key_inter_fixture_and_embedded_frames_are_exact(self) -> None:
        self.assertEqual(len(self.vp8_reference), 119)
        self.assertEqual(
            hashlib.sha256(self.vp8_reference).hexdigest(),
            "5794e6d8bd83a75498d7a471910a7fb2da413056821c216ee44a3400752102cf",
        )
        self.assertEqual(struct.unpack_from("<I", self.vp8_reference, 24)[0], 2)
        first_size = struct.unpack_from("<I", self.vp8_reference, 32)[0]
        first = self.vp8_reference[44 : 44 + first_size]
        second_offset = 44 + first_size
        second_size = struct.unpack_from("<I", self.vp8_reference, second_offset)[0]
        second = self.vp8_reference[second_offset + 12 :]
        self.assertEqual((first_size, second_size, len(second)), (45, 18, 18))
        self.assertEqual(first, extract_c_byte_array(self.source, "vp8_frame_data"))
        self.assertEqual(second[0] & 1, 1)
        self.assertEqual((second[0] >> 4) & 1, 1)
        self.assertEqual(
            hashlib.sha256(second).hexdigest(),
            "d2f8d5025e445be9d75dda6f3c90cce03dba5c83492846ed147ee8c673c57c17",
        )
        self.assertEqual(
            extract_c_byte_array(self.source, "vp8_inter_frame_data"), second
        )

    def test_vp8_default_probability_tables_are_pinned(self) -> None:
        coeff = extract_c_hex_string(self.source, "vp8_default_coeff_probs_hex")
        self.assertEqual(len(coeff), 1056)
        self.assertEqual(
            hashlib.sha256(coeff).hexdigest(),
            "3234d2f1df76ac054b3882e1ab968e0bcfbce29ffcf349e37c843500ef80767e",
        )
        mv_block = re.search(
            r"static const uint8_t vp8_default_mv_probs\[2\]\[19\] = \{"
            r"(?P<body>.*?)\n\};",
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(mv_block)
        self.assertEqual(
            [int(value) for value in re.findall(r"\b\d+\b", mv_block["body"])],
            [162, 128, 225, 146, 172, 147, 214, 39, 156, 128,
             129, 132, 75, 145, 178, 206, 239, 254, 254,
             164, 128, 204, 170, 119, 235, 140, 230, 228, 128,
             130, 130, 74, 148, 180, 203, 236, 254, 254],
        )

    def test_h264_controls_match_the_pinned_baseline_idr(self) -> None:
        for value in (
            "sps->profile_idc = 66U",
            "V4L2_H264_SPS_CONSTRAINT_SET0_FLAG",
            "V4L2_H264_SPS_CONSTRAINT_SET1_FLAG",
            "sps->level_idc = 10U",
            "sps->pic_order_cnt_type = 2U",
            "sps->pic_width_in_mbs_minus1 = 3U",
            "sps->pic_height_in_map_units_minus1 = 3U",
            "pps->pic_init_qp_minus26 = -16",
            "pps->chroma_qp_index_offset = -2",
            "pps->second_chroma_qp_index_offset = -2",
            "decode->nal_ref_idc = 3U",
            "decode->dec_ref_pic_marking_bit_size = 2U",
            "V4L2_H264_DECODE_PARAM_FLAG_IDR_PIC",
            "V4L2_STATELESS_H264_DECODE_MODE_FRAME_BASED",
            "V4L2_STATELESS_H264_START_CODE_ANNEX_B",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.source)
        self.assertIn("memset(scaling, 16, sizeof(*scaling))", self.source)

    def test_vp8_controls_match_the_pinned_keyframe(self) -> None:
        for value in (
            "frame->lf.level = 1U",
            "frame->quant.y_ac_qi = 4U",
            "frame->coder_state.range = 192U",
            "frame->coder_state.value = 22U",
            "frame->coder_state.bit_count = 3U",
            "frame->prob_skip_false = 48U",
            "frame->num_dct_parts = 1U",
            "frame->first_part_size = 24U",
            "frame->first_part_header_bits = 109U",
            "frame->dct_part_sizes[0] = 11U",
            "V4L2_VP8_FRAME_FLAG_KEY_FRAME",
            "V4L2_VP8_FRAME_FLAG_SHOW_FRAME",
            "V4L2_VP8_FRAME_FLAG_MB_NO_SKIP_COEFF",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.source)

    def test_interframe_controls_bind_the_first_capture_timestamp(self) -> None:
        for value in (
            "REFERENCE_TIMESTAMP_NS UINT64_C(1000000000)",
            "sps->max_num_ref_frames = reference_mode ? 1U : 0U",
            "decode->frame_num = 1U",
            "decode->dec_ref_pic_marking_bit_size = 1U",
            "V4L2_H264_DECODE_PARAM_FLAG_PFRAME",
            "decode->dpb[0].reference_ts = REFERENCE_TIMESTAMP_NS",
            "V4L2_H264_FRAME_REF",
            "V4L2_H264_DPB_ENTRY_FLAG_VALID",
            "V4L2_H264_DPB_ENTRY_FLAG_ACTIVE",
            "frame->lf.level = 5U",
            "frame->quant.y_ac_qi = 43U",
            "frame->coder_state.range = 177U",
            "frame->coder_state.value = 2U",
            "frame->coder_state.bit_count = 2U",
            "frame->prob_skip_false = 1U",
            "frame->prob_intra = 1U",
            "frame->prob_last = 255U",
            "frame->prob_gf = 128U",
            "frame->first_part_size = 14U",
            "frame->first_part_header_bits = 86U",
            "frame->dct_part_sizes[0] = 1U",
            "frame->last_frame_ts = REFERENCE_TIMESTAMP_NS",
            "frame->golden_frame_ts = REFERENCE_TIMESTAMP_NS",
            "frame->alt_frame_ts = REFERENCE_TIMESTAMP_NS",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.source)
        self.assertIn(
            "static const uint8_t inter_y_mode_probs[4] = {112, 86, 140, 37}",
            self.source,
        )
        self.assertIn(
            "static const uint8_t inter_uv_mode_probs[3] = {162, 101, 204}",
            self.source,
        )

    def test_reference_modes_hold_two_capture_buffers_and_validate_identity(self) -> None:
        for value in (
            "CODEC_H264_REFERENCE",
            "CODEC_VP8_REFERENCE",
            'strcmp(argv[1], "h264-ref")',
            'strcmp(argv[1], "vp8-ref")',
            "capture_buffer_count = 2U",
            "requested_frames = 2U",
            "uint32_t capture_index = is_reference_mode(mode) ? frame_index : 0U",
            "queue_capture(video_fd, capture_index, capture_buffer)",
            "validate_reference_capture(&dequeued_capture, capture_index",
            "buffer->timestamp.tv_sec != expected_seconds",
            "buffer->timestamp.tv_usec != 0",
            "reference_frames=%s",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.source)
        self.assertRegex(
            self.source,
            r"for \(uint32_t index = capture_buffer_count; index > 0U; --index\)",
        )
        self.assertNotIn("queue_capture(video_fd, &capture_buffer)", self.source)

    def test_exact_identity_request_api_and_output_validation(self) -> None:
        for value in (
            "hantro-vpu",
            "rockchip,px30-vpu-dec",
            "platform:ff442000.video-codec",
            "V4L2_PIX_FMT_H264_SLICE",
            "V4L2_PIX_FMT_VP8_FRAME",
            "V4L2_PIX_FMT_NV12",
            "V4L2_BUF_CAP_SUPPORTS_REQUESTS",
            "V4L2_CTRL_WHICH_REQUEST_VAL",
            "V4L2_BUF_FLAG_REQUEST_FD",
            "MEDIA_IOC_REQUEST_ALLOC",
            "MEDIA_REQUEST_IOC_REINIT",
            "MEDIA_REQUEST_IOC_QUEUE",
            "request_fd < 0",
            "V4L2_BUF_FLAG_ERROR",
            "row[x] != expected",
            "row[x] != 128U",
            "0x0833461a6e018325",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.source)
        self.assertGreaterEqual(self.source.count("validate_decoder_identity"), 3)
        self.assertGreaterEqual(self.source.count("validate_media_identity"), 3)

    def test_no_filesystem_or_system_mutation(self) -> None:
        for pattern in (
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
        ):
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, self.source))
        self.assertIn("writes no target file", self.runbook)
        self.assertRegex(self.runbook, r"do not install it into\s+p2")

    def test_cleanup_timeout_signal_and_markers_are_explicit(self) -> None:
        for value in (
            "VIDIOC_STREAMOFF",
            "munmap(mapped->address",
            "request.count = 0",
            "WAIT_TIMEOUT_MS 10000L",
            "MAX_FRAME_COUNT 240U",
            "frames must be an integer from 1 to %u",
            "frame_index < requested_frames",
            "frames_verified=%u frames_requested=%u",
            "stop_requested && !operation_failed",
            "cleanup_failed ? \"fail\" : \"pass\"",
            "R46H_HANTRO_CODEC_DECODE result=pass codec=%s",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.source)
        self.assertIn("timeout -s TERM -k 2s 20s", self.runbook)

    def test_runbook_pins_current_host_candidate_and_boundaries(self) -> None:
        source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        self.assertEqual(self.runbook.count(source_hash), 1)
        for digest in (
            "c03078b67bc1de5eed12f4ba8a8932560a455a21e24c0f09c340728057673752",
            "ba6606496410c0f1853ab07df590efb17012bdeb850e233e82b673459241d2eb",
            "77940c19ceed0dc95e9dc63a5580c8112454d6b2453d3a2b4d04f76732fb81ff",
            "29a8523996219507c3e26c0b9b40d21fb83300d2a0b684dbe98bd4bd15e0f65f",
            "a3451b0fe905a3c5ea8143b91cb3d05526fa3f5d16f75f6cf4db26355dd791b6",
            "155b2dca06f96aec0bc76df800466bcf72c39083048bddc8fd5060f0187a8171",
            "a8ffb22d06b9be8995bc09817a0650343a162b35ab027a537210d953c55a4719",
            "5794e6d8bd83a75498d7a471910a7fb2da413056821c216ee44a3400752102cf",
            "d2f8d5025e445be9d75dda6f3c90cce03dba5c83492846ed147ee8c673c57c17",
            NV12_SHA256,
            "3234d2f1df76ac054b3882e1ab968e0bcfbce29ffcf349e37c843500ef80767e",
            "8217c5432ea1881fc7be280b49ab85d18842912cd32b3123ef89ff2c88b8a279",
        ):
            with self.subTest(digest=digest):
                self.assertIn(digest, self.runbook)
        self.assertIn("Hardware status: accepted", self.runbook)
        self.assertIn(
            "hantro-h264-vp8-cold-retry-20260816-0004.bin", self.runbook
        )
        self.assertIn(
            "ec4df16886b66026a75cac71a36e33ec6097a0801db0294bac219aa825c0b32e",
            self.runbook,
        )
        self.assertIn(
            "R46H_HANTRO_CODEC_ACCEPTANCE result=pass codecs=h264,vp8",
            self.runbook,
        )
        self.assertIn("systemd-shutdown[1]: Powering off.", self.runbook)
        self.assertIn("400000/300000/200000/100000 Hz", self.runbook)
        self.assertIn("hantro-h264-vp8-stream-20260816.bin", self.runbook)
        self.assertIn(
            "686a64d05540471c9fa212aaa58b7def91ff85018015fa2d9a454257a5715979",
            self.runbook,
        )
        self.assertIn("frames_verified=1", self.runbook)
        self.assertIn("another 120", self.runbook)
        self.assertIn("inter_frame_verified=false", self.runbook)
        self.assertIn("real-time throughput", self.runbook)
        self.assertIn("reference-frame paths", self.runbook)
        self.assertIn("h264-ref vp8-ref", self.runbook)
        self.assertIn("frames_verified=2 reference_frames=verified", self.runbook)
        self.assertNotIn("have not\nyet been executed on R46H", self.runbook)
        self.assertIn("hantro-reference-20260816.bin", self.runbook)
        self.assertIn(
            "e0799bb41d8de5ef23e88885781045fd9699e8b92e96b45fc4abbba264469b59",
            self.runbook,
        )
        self.assertIn(
            "R46H_HANTRO_REFERENCE_ACCEPTANCE result=pass "
            "codecs=h264-ref,vp8-ref inter_frame_verified=true",
            self.runbook,
        )
        self.assertIn("payload_bytes_total=47", self.runbook)
        self.assertIn("payload_bytes_total=63", self.runbook)
        self.assertIn("zero-byte delta after each command", self.runbook)

    @unittest.skipUnless(
        os.environ.get("R46H_RUN_HANTRO_CODEC_SOFTWARE") == "1",
        "set R46H_RUN_HANTRO_CODEC_SOFTWARE=1 for both FFmpeg fixture gates",
    )
    def test_both_fixtures_software_decode_to_exact_nv12(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        self.assertIsNotNone(ffmpeg)
        cache_root = REPO_ROOT / "mainline/out/.cache"
        with tempfile.TemporaryDirectory(
            prefix="r46h-hantro-codec-software.", dir=cache_root
        ) as temporary:
            temporary_path = Path(temporary)
            cases = (
                ("frame.h264", self.h264, 1),
                ("frame.ivf", self.ivf, 1),
                ("reference.h264", self.h264_reference, 2),
                ("reference.ivf", self.vp8_reference, 2),
            )
            for name, payload, frames in cases:
                with self.subTest(name=name):
                    source = temporary_path / name
                    output = temporary_path / f"{name}.nv12"
                    source.write_bytes(payload)
                    subprocess.run(
                        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i",
                         str(source), "-frames:v", str(frames), "-pix_fmt", "nv12",
                         "-f", "rawvideo", "-y", str(output)],
                        check=True,
                    )
                    decoded = output.read_bytes()
                    self.assertEqual(len(decoded), 6144 * frames)
                    for frame_index in range(frames):
                        frame = decoded[frame_index * 6144 : (frame_index + 1) * 6144]
                        self.assertEqual(
                            hashlib.sha256(frame).hexdigest(), NV12_SHA256
                        )

    @unittest.skipUnless(
        os.environ.get("R46H_RUN_HANTRO_CODEC_BUILD") == "1",
        "set R46H_RUN_HANTRO_CODEC_BUILD=1 for the ARM64 Docker compile gate",
    )
    def test_arm64_probe_builds_with_warnings_as_errors(self) -> None:
        cache_root = REPO_ROOT / "mainline/out/.cache"
        with tempfile.TemporaryDirectory(
            prefix="r46h-hantro-codec-build.", dir=cache_root
        ) as temporary:
            subprocess.run(
                [
                    "docker", "run", "--rm", "--user", f"{os.getuid()}:{os.getgid()}",
                    "-v", f"{SOURCE.parent}:/src:ro", "-v", f"{temporary}:/out",
                    "-w", "/out", "--entrypoint", "/bin/bash", BUILDER, "-lc",
                    "gcc -std=c11 -O2 -Wall -Wextra -Werror "
                    "-o r46h-hantro-codec-decode-probe "
                    "/src/r46h-hantro-codec-decode-probe.c",
                ],
                check=True,
            )
            self.assertTrue(
                (Path(temporary) / "r46h-hantro-codec-decode-probe").is_file()
            )


if __name__ == "__main__":
    unittest.main()
