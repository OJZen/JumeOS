# R46H Hantro MPEG-2 decode probe

`r46h-hantro-mpeg2-decode-probe.c` is a bounded, unprivileged V4L2 Request
API gate for the R46H Hantro decoder. It submits one MPEG-2 intra frame to the
exact decoder and media-request nodes, dequeues one NV12 frame, validates all
6,144 logical output bytes and releases every request, stream and MMAP buffer.
It writes no target file. The binary and all health scratch belong only under
`/run/user/1000`; do not install it into p2.

The probe fails closed unless the two open character-device FDs remain bound to
their non-symlink paths and report these identities:

- video driver `hantro-vpu`;
- card `rockchip,px30-vpu-dec`;
- bus `platform:ff442000.video-codec`;
- media driver and bus with the same exact values;
- streaming plus multi-planar mem2mem capabilities;
- stateless `MG2S` output with Request API support and `NV12` capture;
- exact 64x64 formats with one memory plane.

The fixture is a 137-byte, intra-only MPEG-2 elementary stream. Its SHA-256 is
`8dd60e2ed78b0d364e6d071c3ea2d410be3da3d48a8ce086e7e1deacc20d8223`.
The four slices begin at zero-based byte offset 47, occupy 90 bytes and have
SHA-256
`5c0718147bd0a0dd3e849c35bdd197b220ee03fea356d62f9af8684ba9fa1aac`.
The checked-in Base64 is
`fixtures/r46h-hantro-mpeg2-quadrants.m2v.b64`.

Independent FFmpeg 8.1.2 software decoding produces a 6,144-byte NV12 frame
with SHA-256
`7ed819ce0022734308195d983899a72cc5cbbc40bf849b358dab4b33e49d6fd0`:
the Y plane contains exact 32, 96, 160 and 224 quadrants and every UV byte is
128. The C probe independently checks every logical byte and the packed FNV-1a
diagnostic `0833461a6e018325`; padding is intentionally excluded.

This is one real MPEG-2 hardware decode. It does not prove H.264 or VP8,
inter-frame references, every resolution or format, or display presentation.
It does not prove sustained decoding.

## Build and ephemeral transfer

The accepted source SHA-256 is
`6b4e6c310be73e302266b567df5e4669bf0035cc72f221d366c17a7a869f6aa9`.
Build it in the existing external-cache builder environment:

```bash
cache=$(mktemp -d "$PWD/mainline/out/.cache/r46h-hantro-decode-build.XXXXXX")
trap 'rm -rf -- "$cache"' EXIT HUP INT TERM
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/mainline/bringup-tests:/src:ro" \
  -v "$cache:/out" -w /out --entrypoint /bin/bash \
  arkos4clone/r46h-kernel-builder:trixie-arm64 \
  -lc 'gcc -std=c11 -O2 -Wall -Wextra -Werror \
    -o r46h-hantro-mpeg2-decode-probe \
    /src/r46h-hantro-mpeg2-decode-probe.c'
```

The accepted 72,024-byte ARM64 binary SHA-256 is
`40ba4aa960ac873654b9c8641a889ab00157eb2e029d5bb1164fe2196059b13e`.
Transfer that exact binary through the existing serial gzip/Base64 path,
publish it under `/run/user/1000/r46h-hantro-mpeg2-decode-probe`, and verify
its hash before execution.

## Bounded run

Capture `dmesg`, `/sys/fs/ext4/mmcblk0p2/errors_count` and failed units before
and after. Then run exactly one probe with the outer deadline:

```bash
timeout -s TERM -k 2s 20s \
  /run/user/1000/r46h-hantro-mpeg2-decode-probe \
  /dev/video1 /dev/media0
status=$?
printf 'R46H_HANTRO_DECODE_COMMAND_EXIT status=%d\n' "$status"
```

PASS requires all of the following:

- exactly one final `R46H_HANTRO_MPEG2_DECODE result=pass ... cleanup=pass`;
- `width=64 height=64 slice_bytes=90 nv12_bytes=6144` and FNV-1a
  `0833461a6e018325`;
- command status 0;
- no new Hantro, VPU, IOMMU, DMA or scheduler fault in the bounded dmesg delta;
- unchanged zero ext4 error count and zero failed units;
- removal of the transferred binary and all health scratch from target tmpfs.

## Accepted 2026-08-16 result

The accepted binary ran once on
`6.12.99-r46h-mainline-v0.8-bootloader-handoff`. The exact decoder and media
identities matched, `MG2S` negotiated an 8,192-byte output buffer, and `NV12`
negotiated a 64-byte stride with a 6,144-byte capture buffer. The Request API
completed, both queues dequeued without `V4L2_BUF_FLAG_ERROR`, every logical
NV12 byte matched the four-quadrant fixture, FNV-1a was
`0833461a6e018325`, cleanup passed and the command exited 0.

The independent health envelope recorded ext4 `0 -> 0`, failed units `0 ->
0`, an unchanged 30,790-byte dmesg snapshot, no ring wrap or fault match, and
`R46H_HANTRO_ACCEPTANCE result=pass cleanup=pass`. The transferred binary and
health scratch were removed from target tmpfs before a controlled poweroff.

The durable serial receipt is
`mainline/out/r46h-serial-logs/hantro-mpeg2-decode-live-20260816.bin`, 25,933
bytes with SHA-256
`cc6783b41d770ddc3e9ec0bc0098eac40ba19f4c4c8dc92999244604bff2be88`.
This closes one MPEG-2 intra-frame decoder data path. Do not repeat it without
a decoder, kernel or hardware change. H.264, VP8, inter-frame references,
sustained throughput and broader format coverage remain open.
