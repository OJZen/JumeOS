# R46H Moonlight test client

Temporary Debian 13 / SDL prototype. Project scope and hardware evidence are
linked from [Game Streaming](../../docs/GAME-STREAMING.md); this is not a rootfs
release or a claim of hardware decoding or macOS virtual-gamepad support.

The separate [Moonlight Qt candidate](QT-CANDIDATE.md) owns the prepared
ARM/V4L2 package and its pending hardware gate. Keep this accepted client as fallback.

## Local changes

[r46h-ui.patch](r46h-ui.patch) applies to Moonlight Embedded v2.7.1 at
`775444287305849ebdf4736c75298ad0713e2d5d`. It changes both SDL and evdev exit
chords to **L1 + R1** and updates upstream help. The SDL overlay displays client
presentations per second and process CPU, sampled over elapsed time once per
second. CPU 100% means one core; it may exceed 100%. FPS is not the requested
stream rate, unique host frames, or end-to-end latency. Initial values are `-`.

The 3×5 bitmap glyphs use SDL already required by the client; the texture is
rebuilt once per second and copied once per displayed frame. The patch includes
one executable check for timing, multi-core CPU, tick wrap, unavailable CPU
samples and actual headless SDL texture rendering. The Docker build runs it.

## Build

Run from the repository root. Use an empty task-owned source directory; retain
existing evidence instead of resetting an unfamiliar checkout.

```sh
stream_cache="$PWD/mainline/out/.cache/r46h-streaming"
git clone --branch v2.7.1 --depth 1 --recurse-submodules \
  https://github.com/moonlight-stream/moonlight-embedded.git "$stream_cache/moonlight-embedded"
test "$(git -C "$stream_cache/moonlight-embedded" rev-parse HEAD)" = \
  775444287305849ebdf4736c75298ad0713e2d5d
git -C "$stream_cache/moonlight-embedded" apply \
  "$PWD/mainline/gaming-moonlight/r46h-ui.patch"
git -C "$stream_cache/moonlight-embedded" apply \
  "$PWD/mainline/gaming-moonlight/r46h-audio.patch"
BUILDX_CONFIG="$stream_cache/buildx" docker build --platform linux/arm64 \
  -t arkos4clone/r46h-moonlight-test:v2.7.1-audio1024 \
  -f mainline/gaming-moonlight/Dockerfile "$stream_cache/moonlight-embedded"
docker run --rm --platform linux/arm64 --entrypoint cat \
  arkos4clone/r46h-moonlight-test:v2.7.1-audio1024 /moonlight-test.tar.gz \
  > "$stream_cache/moonlight-audio.tar.gz"
```

The [Dockerfile](Dockerfile) reuses the local arm64 PPSSPP builder. The tested
base image ID was `sha256:6381ff02e8a1bb5eda383ee37f45ae9312c412c7e242cc659bcd26a57d5cd548`.
APT dependencies are not snapshot-pinned: this is build/run proof, not a
reproducible release. The tar contains `build-packages.txt` and licenses, and
bundles only the two Avahi runtime libraries missing from the current card.

## Frame cadence analysis

The retained client log contains 3030 frame-number gaps: all 3028 even frame
numbers from 2 through 6056, plus frames 2523 and 4667. Only those last two
frames report incomplete FEC data. Moonlight's
[depacketizer](https://github.com/moonlight-stream/moonlight-common-c/blob/b126e481a195fdc7152d211def17190e3434bcce/src/VideoDepacketizer.c#L800)
prints `Network dropped` for sequence gaps before SDL decoding or presentation.
That label alone cannot establish network loss. The two incomplete frames are
separate reception failures and remain unexplained.

Pinned Sunshine `14ffa6fdaa53f7b51512be2b3d24f3939695403c` forces
`max_ref_frames=1` for H.264 VideoToolbox in
[video.cpp](https://github.com/LizardByte/Sunshine/blob/14ffa6fdaa53f7b51512be2b3d24f3939695403c/src/video.cpp#L1137).
Its FFmpeg dependency maps that option to VideoToolbox `ReferenceBufferCount`;
encoded packet PTS becomes the transmitted frame index. Skipped encoder output
can therefore produce the observed client message without Wi-Fi dropping it.

[probe-videotoolbox.py](probe-videotoolbox.py) reproduced alternate-frame loss
on this Mac using synthetic 640×480/60 H.264 input, with no capture, network or
R46H involved. Only the reference-buffer setting differs between the two runs:

| Setting | Input frames | Output packets | Packet PTS |
| --- | ---: | ---: | --- |
| `max_ref_frames=1` | 120 | 60 | 0, 2, …, 118 |
| `max_ref_frames=0` (automatic) | 120 | 120 | 0, 1, …, 119 |

The probe uses installed FFmpeg 9.0.1, not Sunshine's statically linked FFmpeg
build. The later Sunshine-to-R46H candidate test retained the original client
and stream settings: 257 HUD samples reached 55–61 FPS (median 60), CPU 89–130%
(median 97%), with zero frame-gap messages. The operator accepted picture/audio.
This closes the alternating-gap failure for this sample; it does not establish
long-run network reliability or the cause of the speaker pops.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B mainline/gaming-moonlight/probe-videotoolbox.py --self-test
PYTHONDONTWRITEBYTECODE=1 python3 -B mainline/gaming-moonlight/probe-videotoolbox.py \
  mainline/out/.cache/r46h-streaming/offline-analysis/vt-new-sample
```

The output directory must be new. The script records commands, FFmpeg version,
packet PTS and encoder errors; a failed encoder is not a cadence result. The
accepted run and source hashes live under the external streaming cache's
`offline-analysis/vt-reference-proof/` and `offline-analysis/cadence-analysis.json`.

[sunshine-h264-reference-buffer.patch](sunshine-h264-reference-buffer.patch)
removes only the H.264 override from the pinned Sunshine source. Exact patch
application and the unaffected HEVC/AV1 options were checked. The isolated macOS
candidate is built; its host checks are described below. Repeat the same stream
settings with the accepted client before changing Wi-Fi, client decoder,
buffers or the rootfs image.

## Sunshine host candidate

The external streaming cache contains `sunshine-candidate/Sunshine.app`, its
`receipt.json` and `SHA256SUMS`. The arm64 Release build, bundled-library check,
ad-hoc signature verification and version command passed. This is a local test
signature, not the official publisher signature or notarization. After unlocking
the Mac, startup captured the probe frame, found the H.264 VideoToolbox encoder
and returned HTTP 200 with `SUNSHINE_SERVER_FREE` from `serverinfo`. Target
delivery passed the sample above. A locked Mac stalls in `av_display_t::dummy_img`;
keep it awake and unlocked during the attended test.

The receipt records the prepared inputs: Sunshine's pinned source, its required
submodules, official Boost/FFmpeg archives from build-deps `v2026.516.30821`,
locally built static miniupnpc 2.3.3, and installed Opus/OpenSSL. Source files
were checked against the upstream Git blob hashes; only `src/video.cpp` differs.
The same official App supplies the web assets. These dependency choices and
local signing mean this is not a byte-reproducible official release build.

With those inputs prepared under the cache and the patch applied once:

```sh
stream_cache="$PWD/mainline/out/.cache/r46h-streaming"
stream_deps="$stream_cache/sunshine-deps"
mkdir -p "$stream_cache/sunshine-build/assets"
cp -R "$stream_cache/unpacked/Sunshine/Sunshine.app/Contents/Resources/assets/." \
  "$stream_cache/sunshine-build/assets/"
PKG_CONFIG_PATH="$stream_deps/miniupnpc/lib/pkgconfig:/opt/homebrew/opt/opus/lib/pkgconfig" \
BUILD_VERSION=2026.516.143833 BRANCH=r46h-h264-ref-auto \
COMMIT=14ffa6fdaa53f7b51512be2b3d24f3939695403c \
cmake -S "$stream_cache/sunshine-source" -B "$stream_cache/sunshine-build" \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$stream_cache/sunshine-candidate" \
  -DBUILD_DOCS=OFF -DBUILD_TESTS=OFF -DBOOST_USE_STATIC=ON -DSUNSHINE_ENABLE_TRAY=ON \
  -DCMAKE_PREFIX_PATH="$stream_deps/boost;/opt/homebrew/opt/opus;$stream_deps/miniupnpc" \
  -DFFMPEG_PREPARED_BINARIES="$stream_deps/ffmpeg" \
  -DOPENSSL_ROOT_DIR=/opt/homebrew/opt/openssl@3 \
  -DCMAKE_EXE_LINKER_FLAGS="-L$stream_deps/miniupnpc/lib" \
  -DSUNSHINE_PUBLISHER_NAME='R46H local test'
cmake --build "$stream_cache/sunshine-build" --target sunshine -j 6
SHOULD_SIGN=false cmake --install "$stream_cache/sunshine-build"
codesign --force --deep --sign - "$stream_cache/sunshine-candidate/Sunshine.app"
codesign --verify --deep --strict "$stream_cache/sunshine-candidate/Sunshine.app"
```

Build tray support because this revision's macOS code still links tray symbols;
disable it in the runtime config. Building only `sunshine` reuses web assets and
skips npm. Always pass the absolute isolated config **before** `--version` or
`-0`. Upstream still creates `~/.config/sunshine` even with explicit file paths;
remove that directory afterward only if it was task-created and remains empty.
Keep the Mac awake and unlocked for capture. Never register a host service.

## Audio buffer comparison

The operator subsequently noticed audio lagging behind video. The original SDL
audio code requests 4096 samples. On R46H this produced a 48 kHz stereo PCM
period of 4096 and buffer of 8192 samples; the retained running-state snapshot
had 8152 queued frames, about 170 ms at the sound device alone.

[r46h-audio.patch](r46h-audio.patch) sets `want.samples=0` so the existing
[SDL 2 audio configuration](https://github.com/libsdl-org/SDL/blob/release-2.32.4/src/audio/SDL_audio.c#L1287)
can honor `SDL_AUDIO_SAMPLES`. The bounded launcher supplies 1024. This keeps
the native calibration setting available without a new client option or parser.
The candidate built and passed the HUD check. On-device PCM now uses period
1024/buffer 2048; running snapshots had 1984–2040 queued frames, about 41–43 ms.
The bounded five-minute run logged 294 HUD samples: 56–61 FPS (median 60), CPU
86–100% (median 94%), no frame-gap messages and no logged audio underrun/error.
Timeout status 124 restored mixer/frontend with status 0. The attended repeat
passed subjective comparison: the operator heard no problematic audio delay or
pops, then confirmed exit. Its 86 HUD samples were 57–61 FPS (median 60), CPU
87–124% (median 98%), with no frame-gap or audio-error messages. Client exit and
mixer/frontend restoration were all status 0. Device queue time is not measured
end-to-end A/V offset; this short sample does not establish long-run pop freedom.

The unchanged-audio video test is retained in streaming cache
`candidate-attended/video-candidate-evidence.tgz` and its extracted
`video-candidate/` directory. L1 + R1 returned client status 0; the operator saw
a temporary black screen before ES-DE recovered without intervention. The
black-screen duration was not measured. Service start success alone does not
prove the menu is already visible.

The smaller-buffer archive is `candidate-attended/audio-candidate-evidence.tgz`;
the extracted `audio-candidate/` holds PCM/health logs and `performance.json`.
`candidate-attended/receipt.json` owns identities, observations and evidence
hashes. The audio client tar is 328934 bytes, SHA-256
`13dd0c9a943bd5b7d26ecf80599878635671f154cec0c6a8424ad6fc2cefc99a`.
Final services had zero restarts, ext4/matched kernel errors were zero, and
`/roms` stayed read-only. Temporary client/host keys and transfer staging were
removed, servers stopped, and serial confirmed controlled poweroff.

The attended repeat is retained separately in `candidate-audio-listen/`:
`audio-listen-evidence.tgz`, extracted `device/` logs and `receipt.json`.
Its UART transfer was SHA-256 verified before target cleanup. The cold listener
received no bytes; a 115200 console connection verified the already-running
device. This repeat adds no cold-boot trace evidence.

## Attended run

Rediscover addresses and verify R46H identity first. Transfer the public tar
through the established transport, check its exact size/SHA-256 on the target,
and extract into task-owned `/run/r46h-moonlight-test` while Moonlight is stopped.
After extraction, restore that directory to owner `ark`, mode 0700; the tar
root entry otherwise replaces its ownership. The launcher rejects a mismatch.
Pair using its private `keys` directory; never include keys, PINs or Sunshine
private state in captured logs.

Copy [run-stream.sh](run-stream.sh) into that directory and run it as root with
the identified Sunshine host as its only argument. It requires this exact p2
v0.17/kernel/card and an active frontend. It reuses the accepted SDL mapping,
starts the client on VT2, and restores the mixer/frontend on exit. The reviewed
launcher uses a disposable systemd unit with a 300-second runtime limit and
10-second stop limit so session-detached children are also cleaned up. Timeout
returns nonzero (the historical GNU timeout launcher returned 124). L1 + R1
should return normally. No unit file or boot service is installed. Busy-client,
process-check and restore failures are covered by `test-gaming-probe.py` with
mock services; this revised launcher still needs a target lifecycle check.
`client-hud.log` captures FPS/CPU; capture wrapper output separately. Never use
`-debug`, which can expose protocol secrets. Archive logs before another run.

The same canonical launcher now also accepts `--qt HOST BINARY_SHA256` for the
[hardware-decoder candidate](QT-CANDIDATE.md). That branch uses its separate
private staging directory, checks the executable hash and dependencies before
stopping the frontend, and sets a 120-second experiment limit. Both branches
share the reviewed cgroup/mixer/frontend recovery; the Qt branch retains native
audio and the combined-pad filter. Host checks cover both argument vectors and
fail-closed preflight. This is preparation for the next device run, not client
selection or installation in the new desktop.

Confirm LCD text, single shoulder buttons staying in-stream, then L1 + R1 return
to ES-DE. Check input/volume services, PCM, filesystem and kernel health. Stop
Sunshine and the public transfer server after attended work; retain evidence,
remove temporary client state, then sync and power off through serial.
