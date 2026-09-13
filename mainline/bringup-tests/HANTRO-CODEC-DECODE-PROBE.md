# R46H Hantro H.264 and VP8 decode probe

`r46h-hantro-codec-decode-probe.c` is a bounded, unprivileged V4L2 Request
API gate for two Hantro decoder formats. The `h264` and `vp8` modes submit
between 1 and 240 independent IDR/key frames. The `h264-ref` and `vp8-ref`
modes instead submit one exact two-frame pair: IDR then P, or key then inter.
Those modes keep the first capture buffer dequeued, bind its copied nanosecond
timestamp in the second request's reference controls, and use a different
capture buffer for the result. Every mode validates all 6,144 logical output
bytes for every frame and then releases every request, stream and buffer. It
writes no target file. The binary and health scratch belong only under
`/run/user/1000`; do not install it into p2.

Hardware status: accepted on 2026-08-16 for one H.264 constrained-baseline IDR
frame, one VP8 keyframe, bounded 120-frame independent-key sessions, and the
exact two-frame H.264 IDR-to-P and VP8 key-to-inter reference paths below. The
reference result proves the pinned fixtures and controls, not arbitrary streams.

The probe fails closed unless both open character-device FDs remain bound to
their non-symlink paths and report these identities:

- video driver `hantro-vpu`;
- card `rockchip,px30-vpu-dec`;
- bus `platform:ff442000.video-codec`;
- media driver and bus with the same exact values;
- streaming plus multi-planar mem2mem capabilities;
- Request API support for `S264` or `VP8F`, with one-plane `NV12` capture;
- exact 64x64 negotiated dimensions.

## Pinned fixtures

The H.264 fixture is a 70-byte Annex B stream containing exactly SPS, PPS and
one IDR NAL. Its SHA-256 is
`c03078b67bc1de5eed12f4ba8a8932560a455a21e24c0f09c340728057673752`.
The driver payload is only its 37-byte IDR slice, including a three-byte Annex
B start code, with SHA-256
`ba6606496410c0f1853ab07df590efb17012bdeb850e233e82b673459241d2eb`.
SPS, PPS, flat scaling matrix and IDR decode parameters are supplied through
the stateless H.264 controls. The checked-in Base64 is
`fixtures/r46h-hantro-quadrants.h264.b64`.

The VP8 fixture is an 89-byte IVF containing one 45-byte keyframe. Their
SHA-256 values are respectively
`77940c19ceed0dc95e9dc63a5580c8112454d6b2453d3a2b4d04f76732fb81ff`
and
`29a8523996219507c3e26c0b9b40d21fb83300d2a0b684dbe98bd4bd15e0f65f`.
The frame tag independently proves keyframe, show-frame, 24-byte first
partition and 64x64 dimensions. Its parsed 1,056-byte default coefficient
probability table is pinned by SHA-256
`3234d2f1df76ac054b3882e1ab968e0bcfbce29ffcf349e37c843500ef80767e`.
The checked-in Base64 is `fixtures/r46h-hantro-quadrants.ivf.b64`.

The H.264 reference fixture is a 646-byte Annex B stream with SHA-256
`a3451b0fe905a3c5ea8143b91cb3d05526fa3f5d16f75f6cf4db26355dd791b6`.
The submitted NAL payloads are its 38-byte IDR and 9-byte P slices, SHA-256
`155b2dca06f96aec0bc76df800466bcf72c39083048bddc8fd5060f0187a8171`
and
`a8ffb22d06b9be8995bc09817a0650343a162b35ab027a537210d953c55a4719`.
The P request binds DPB entry 0 to the first capture timestamp, frame number 0,
PicNum 0 and both field order counts 0. Its checked-in Base64 is
`fixtures/r46h-hantro-quadrants-idr-p.h264.b64`.

The VP8 reference fixture is a 119-byte, two-frame IVF with SHA-256
`5794e6d8bd83a75498d7a471910a7fb2da413056821c216ee44a3400752102cf`.
Its first 45-byte keyframe is the existing pinned payload; its 18-byte inter
frame has SHA-256
`d2f8d5025e445be9d75dda6f3c90cce03dba5c83492846ed147ee8c673c57c17`.
An independent RFC 6386 parser fixed the second frame's full entropy tables,
quantizer 43, loop-filter level 5, bool coder state, one-byte DCT partition and
all three references to the first capture timestamp. Its checked-in Base64 is
`fixtures/r46h-hantro-quadrants-key-inter.ivf.b64`.

Independent FFmpeg software decoding of all four complete fixtures produces
the same 6,144-byte NV12 frame for every decoded picture, with SHA-256
`7ed819ce0022734308195d983899a72cc5cbbc40bf849b358dab4b33e49d6fd0`:
the Y plane contains exact 32, 96, 160 and 224 quadrants and every UV byte is
128. The C probe checks every logical byte and packed FNV-1a diagnostic
`0833461a6e018325`; negotiated padding is intentionally excluded.

The original `h264` and `vp8` modes still submit only independent IDR or key
frames. Their bounded multi-frame form proves repeated request
reinitialization, buffer reuse and queue lifecycle. Only a future accepted
`h264-ref`/`vp8-ref` hardware run can close the two exact reference-frame paths;
even then profiles with B-frames, longer dependency chains, every profile or
resolution, display presentation, error concealment, real-time pacing and
long-duration thermal stability remain open.

## Host gates and build

Run the static gates plus both independent software decodes:

```bash
R46H_RUN_HANTRO_CODEC_SOFTWARE=1 \
  PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/tests/test-r46h-hantro-codec-decode-probe.py -v
```

The current source SHA-256 is
`87ec77c10aa73be79467e03346d09e863abb2b267527c887ff08aec9d9ed4c10`.
Build it in the existing external-cache builder:

```bash
cache=$(mktemp -d "$PWD/mainline/out/.cache/r46h-hantro-codec-build.XXXXXX")
trap 'rm -rf -- "$cache"' EXIT HUP INT TERM
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/mainline/bringup-tests:/src:ro" \
  -v "$cache:/out" -w /out --entrypoint /bin/bash \
  arkos4clone/r46h-kernel-builder:trixie-arm64 \
  -lc 'gcc -std=c11 -O2 -Wall -Wextra -Werror \
    -o r46h-hantro-codec-decode-probe \
    /src/r46h-hantro-codec-decode-probe.c'
```

The current reproducible 72,496-byte ARM64 candidate SHA-256 is
`8217c5432ea1881fc7be280b49ab85d18842912cd32b3123ef89ff2c88b8a279`.
Transfer that exact binary through the existing serial gzip/Base64 path,
publish it under `/run/user/1000/r46h-hantro-codec-decode-probe`, and verify
its hash before either invocation.

## One-boot bounded hardware gate

The optional fifth argument is the exact frame count, from 1 through 240; an
omitted count preserves the original single-frame behavior. Run H.264 and VP8
serially, never concurrently. Capture dmesg,
`/sys/fs/ext4/mmcblk0p2/errors_count` and failed units before the first command
and after each command. Give each invocation its own outer deadline:

```bash
for codec in h264 vp8; do
  status=0
  timeout -s TERM -k 2s 20s \
    /run/user/1000/r46h-hantro-codec-decode-probe "$codec" \
    /dev/video1 /dev/media0 120 || status=$?
  printf 'R46H_HANTRO_CODEC_COMMAND_EXIT codec=%s status=%d\n' \
    "$codec" "$status"
  test "$status" -eq 0 || break
done
```

PASS for each codec requires all of the following:

- exact `R46H_HANTRO_CODEC_PROGRESS` checkpoints through the requested count
  and exactly one final
  `R46H_HANTRO_CODEC_DECODE result=pass codec=h264|vp8 ... cleanup=pass`;
- the exact requested `frames_verified`, `width=64 height=64
  nv12_bytes=6144` and FNV-1a
  `0833461a6e018325`;
- command status 0;
- no new Hantro, VPU, IOMMU, DMA or scheduler fault in its bounded dmesg delta;
- unchanged zero ext4 error count and zero failed units;
- removal of the binary and all health scratch from target tmpfs after both
  commands, followed by controlled poweroff.

If H.264 fails, stop before VP8 unless the failure is proved to be a harmless
host transport or invocation mistake. Preserve the serial receipt for every
attempt; do not overwrite a failed attempt with a later PASS.

## Two-frame reference gate

This gate is deliberately separate from the accepted independent-frame run.
It has no frame-count argument: each command must decode exactly two pictures,
retain capture index 0 as the reference and use capture index 1 for the second
output. Run it only after verifying the current candidate hash above:

```bash
for codec in h264-ref vp8-ref; do
  status=0
  timeout -s TERM -k 2s 20s \
    /run/user/1000/r46h-hantro-codec-decode-probe "$codec" \
    /dev/video1 /dev/media0 || status=$?
  printf 'R46H_HANTRO_REFERENCE_COMMAND_EXIT codec=%s status=%d\n' \
    "$codec" "$status"
  test "$status" -eq 0 || break
done
```

In addition to the ordinary identity, NV12, health and cleanup gates, each
command must report `frames_verified=2 reference_frames=verified`. H.264 must
consume 47 payload bytes total (38 + 9); VP8 must consume 63 (45 + 18). A
timestamp or dequeued-buffer-index mismatch fails before PASS. Run H.264 first
and stop on any failure. A final wrapper may set `inter_frame_verified=true`
only after both commands return 0, health stays unchanged, tmpfs cleanup passes
and the device reaches controlled poweroff.

## 2026-08-16 reference-frame hardware result

The accepted run used kernel
`6.12.99-r46h-mainline-v0.8-bootloader-handoff`, `/dev/video1` and
`/dev/media0`. The transferred 72,496-byte ARM64 probe matched SHA-256
`8217c5432ea1881fc7be280b49ab85d18842912cd32b3123ef89ff2c88b8a279`.
The 101,516-byte serial receipt is
`mainline/out/r46h-serial-logs/hantro-reference-20260816.bin`, SHA-256
`e0799bb41d8de5ef23e88885781045fd9699e8b92e96b45fc4abbba264469b59`.

H.264 ran first and returned 0 after decoding exactly IDR then P. Its final
marker reported `payload_bytes_total=47`, `frames_verified=2`,
`reference_frames=verified`, the exact 6,144-byte NV12 image and FNV-1a
`0833461a6e018325`. VP8 then returned 0 for exactly key then inter with the
same output checks, `payload_bytes_total=63`, `frames_verified=2` and
`reference_frames=verified`. Both invocations reported `cleanup=pass`.

The preflight and both post-codec gates kept ext4 errors and failed units at
zero. The 30,674-byte dmesg snapshot remained a byte-for-byte prefix with a
zero-byte delta after each command, so the bounded fault count was zero. All
transferred binary and health files were removed from target tmpfs before the
receipt emitted:

```text
R46H_HANTRO_REFERENCE_ACCEPTANCE result=pass codecs=h264-ref,vp8-ref inter_frame_verified=true ext4_errors=0 failed_units=0 dmesg_faults=0 cleanup_remaining=0
```

The device then reached `systemd-shutdown[1]: Powering off.` and the serial
line stayed silent. The same receipt preserves an earlier rejected whole-line
Base64 transfer that failed decoding; its damaged output failed before probe
execution. Consumers must select the later exact binary SHA, both command-exit
status 0 markers, both zero-health markers, the final acceptance marker and the
shutdown tail.

This closes only the two pinned reference transitions. It does not establish
H.264 B-frames, other profiles or resolutions, VP8 streams with different
entropy/update behavior, presentation timing, real-time throughput, long-run
thermal stability or error recovery.

## 2026-08-16 single-frame hardware result

The accepted run used kernel
`6.12.99-r46h-mainline-v0.8-bootloader-handoff`, `/dev/video1` and
`/dev/media0`. The transferred 72,304-byte ARM64 probe matched SHA-256
`ce9def4a0a701641cf18d715a3603e904f267f2fc1b717e9e0ac8493b822c736`.
The 33,584-byte serial receipt is
`mainline/out/r46h-serial-logs/hantro-h264-vp8-cold-retry-20260816-0004.bin`
with SHA-256
`ec4df16886b66026a75cac71a36e33ec6097a0801db0294bac219aa825c0b32e`.

The H.264 invocation returned 0, consumed the pinned 37-byte IDR payload and
produced the exact 6,144-byte NV12 quadrant frame. The VP8 invocation then
returned 0, consumed the pinned 45-byte keyframe and produced the same exact
frame. Both reported FNV-1a `0833461a6e018325` and `cleanup=pass`. Before and
after each command, ext4 remained `0 -> 0`, failed units remained zero, and
the 30,851-byte dmesg snapshot was byte-identical, so each bounded delta was
empty. Final tmpfs cleanup passed and the log reached
`R46H_HANTRO_CODEC_ACCEPTANCE result=pass codecs=h264,vp8 ext4_errors=0
failed_units=0 dmesg_faults=0 cleanup=pass`, followed by
`systemd-shutdown[1]: Powering off.`

This accepts exactly the two single-frame hardware paths described above. It
does not prove H.264 P-frames or profiles with B-frames, VP8 reference frames,
inter-frame reference management, other profiles or resolutions, error
concealment, presentation, or sustained decoding.

One preceding power-on attempt never reached userland and repeatedly printed
the `mmc1` 400000/300000/200000/100000 Hz bus-speed sequence. Treat that
sequence as a boot-media detection/contact diagnostic, not a codec failure.
Preserve its log, fully remove power for at least five seconds, and retry before
disturbing the TF card or CH340. Do not run or score this codec gate unless
Linux reaches the exact preflight identity and health checks above.

## 2026-08-16 bounded continuous-session result

The extended 72,360-byte candidate matched SHA-256
`52bca5aa6efc390363bd9e5c727ffdbb4aab5013ed7ee8b52024cb426a424c57`.
Its original four-argument H.264 command first passed with
`frames_verified=1`, proving interface compatibility. A new H.264 invocation
then completed 120 requests in one streaming session, followed by an
independent VP8 invocation that completed another 120. Every one of the 240
outputs passed the full 6,144-byte NV12 comparison and FNV-1a
`0833461a6e018325`; both final markers reported exit status 0 and
`cleanup=pass`.

For each 120-frame session, dmesg was byte-identical at 30,926 bytes before and
after, ext4 remained `0 -> 0`, failed units remained zero, and the fault delta
was empty. The final acceptance marker explicitly records
`inter_frame_verified=false`, all target tmpfs files were removed, and the
device reached `systemd-shutdown[1]: Powering off.`

The 23,603-byte serial receipt is
`mainline/out/r46h-serial-logs/hantro-h264-vp8-stream-20260816.bin`, SHA-256
`686a64d05540471c9fa212aaa58b7def91ff85018015fa2d9a454257a5715979`.
It also preserves two rejected pre-execution attempts caused by an expired sudo
timestamp and the resulting tmpfs cleanup. Consumers must select the final
hash-verified candidate, both 120-frame PASS markers, both zero-health markers,
the final acceptance marker and shutdown tail; the earlier attempts executed
no 120-frame request.

This closes a short bounded continuous request/buffer lifecycle for independent
H.264 IDR and VP8 keyframes. It does not close either codec's reference-frame
path, long-duration or real-time throughput, thermal stability, or the other
format/profile/resolution boundaries above.
