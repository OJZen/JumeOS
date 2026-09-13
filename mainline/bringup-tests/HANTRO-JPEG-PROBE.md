# R46H Hantro JPEG encode probe

`r46h-hantro-jpeg-probe.c` is a bounded, unprivileged V4L2 mem2mem data-path
gate for the R46H Hantro encoder. It sends one deterministic 96x32 three-plane
YUV420 frame through `/dev/video0`, dequeues the encoded capture buffer,
validates its JFIF, baseline-SOF dimensions and JPEG end markers, then streams
off and unmaps every buffer. The default mode writes no file. The optional
`--emit-base64` mode prints the encoded JPEG to the serial receipt so a host can
decode it independently without writing the target root filesystem.

The probe fails closed unless the open character-device FD remains the same
inode and `st_rdev` as the non-symlink path and reports all of these identities:

- driver `hantro-vpu`;
- card `rockchip,px30-vpu-enc`;
- bus `platform:ff442000.video-codec`;
- streaming plus multi-planar mem2mem capabilities;
- exact 96x32 `YM12` input with three planes and JPEG capture with one plane.

This is an actual single-frame JPEG encode, not another capability query. It
does not prove H.264/MPEG-2/VP8 decoding, sustained video throughput, every
pixel format or media-request correctness. Decoder coverage is a separate gate;
one MPEG-2 intra-frame path later passed in
[`HANTRO-MPEG2-DECODE-PROBE.md`](HANTRO-MPEG2-DECODE-PROBE.md), while H.264,
VP8 and sustained decode remain open.

## Build and ephemeral transfer

The accepted source SHA-256 is
`a7cef1df4ee01bbf723d971293a710521147c75c4c74c8716ca8b79ffbb914a0`.
The accepted ARM64 binary was built inside the existing
`arkos4clone/r46h-kernel-builder:trixie-arm64` image with:

```bash
cache="$PWD/mainline/out/.cache/r46h-hantro-probe-build"
mkdir -p "$cache"
docker run --rm --user 501:20 \
  -v "$PWD/mainline/bringup-tests:/src:ro" \
  -v "$cache:/out" -w /out --entrypoint /bin/bash \
  arkos4clone/r46h-kernel-builder:trixie-arm64 \
  -lc 'gcc -std=c11 -O2 -Wall -Wextra -Werror \
    -o r46h-hantro-jpeg-probe-accepted \
    /src/r46h-hantro-jpeg-probe.c'
```

Its SHA-256 was
`dfa0a9c0b4cda9855c8ef58b1dfdc7a12b5546575cee0400023c58f763515b37`.
Before a run, transfer and re-hash that exact binary under
`/run/user/1000`; do not install it into p2:

```bash
expected=dfa0a9c0b4cda9855c8ef58b1dfdc7a12b5546575cee0400023c58f763515b37
printf '%s' '<reviewed-gzip-base64>' | base64 -d | gzip -dc \
  > /run/user/1000/.r46h-hantro-jpeg-probe.incoming
chmod 0700 /run/user/1000/.r46h-hantro-jpeg-probe.incoming
mv /run/user/1000/.r46h-hantro-jpeg-probe.incoming \
  /run/user/1000/r46h-hantro-jpeg-probe
printf '%s  %s\n' "$expected" /run/user/1000/r46h-hantro-jpeg-probe \
  | sha256sum -c -
```

Run one process with an outer hard deadline. Capture `dmesg`, the ext4 error
counter and failed units before and after as independent health gates:

```bash
timeout -s TERM -k 2s 20s \
  /run/user/1000/r46h-hantro-jpeg-probe /dev/video0 --emit-base64
status=$?
printf 'R46H_HANTRO_COMMAND_EXIT status=%d\n' "$status"
```

Only one final `R46H_HANTRO_JPEG result=pass ... cleanup=pass`, exit status 0,
an empty bounded dmesg delta, an unchanged zero ext4 error counter and zero
failed units form a PASS. Remove the transferred binary and any health scratch
from `/run/user/1000` after retaining the serial log.

## Accepted 2026-08-15 result

The exact accepted binary ran on
`6.12.99-r46h-mainline-v0.8-bootloader-handoff`. It negotiated Y/U/V buffer
sizes `3072,768,768`, submitted 4,608 logical input bytes and returned a
778-byte JPEG with FNV-1a diagnostic `4be796a039147d77`. The command exited 0,
cleanup passed, the dmesg delta was empty, ext4 stayed `0 -> 0`, and failed
units stayed zero.

The emitted JPEG was decoded independently on macOS by both `file` and `sips`
as baseline three-component JFIF, 96x32. Its SHA-256 is
`d075cdac6b5ad5de736aa6fdf4d1d2f1fc15605ff7902856f4df8a1a0468683c`.
This closes the JPEG encoder data-path question. It does not close the decoder
or general video-codec gate by itself. The separate MPEG-2 intra-frame result
closes only that decoder path. The accepted JPEG test should not be repeated
without a driver, kernel or hardware change.

The primary durable receipt for the exact hardened source and binary is
`mainline/out/r46h-serial-logs/v08-hantro-final-hardened-20260815.bin`, 7,382
bytes, SHA-256
`f5816a87dc8e24bae332717ac42a2c44152734bd1d2972dd3165c0e0fd32bfd5`.
It records `R46H_HANTRO_FINAL_EXIT status=0`, an empty bounded dmesg delta,
`R46H_HANTRO_FINAL_POST probe=0 fault_count=0 ext4_before=0 ext4_after=0
failed_units=0`, and final target-tmpfs cleanup with zero residue. The JPEG
base64 in that receipt independently decodes to the SHA-256 above.

The earlier exploratory receipt remains at
`mainline/out/r46h-serial-logs/v08-hantro-path-retry-20260815.bin`, 147,573
bytes, SHA-256
`516560bdeaf68487777040714bf7bda95a7dd6b427918870988a325257b48f28`.
It deliberately retains the safe failed attempts that established the
driver's three-plane buffer contract, but those attempts are not accepted
results.
