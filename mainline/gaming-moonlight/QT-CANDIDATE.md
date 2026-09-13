# Moonlight Qt hardware-decoder candidate

Revision v5, 2026-09-11: **NATIVE STATISTICS HOST PASS / DEVICE UNTESTED**.
V4 retains **FRESH LIST REQUEST HOST LOGIC PASS / DEVICE UNTESTED**.
V3 retains **SHORT DEVICE HUD/A/V/RETURN PASS / LONG SESSION OPEN**.
Revision v2 retains **R46H HANTRO/RETURN PASS / HUD, PACING AND AUDIO OPEN**.
The official baseline passed the 2026-09-06 machine hardware-decode sample.
No candidate has replaced the accepted Embedded client.
[Game Streaming](../../docs/GAME-STREAMING.md#next-gate) owns project priority.

The [attended desktop integration record](../gaming-shell/STREAMING.md#attended-result-2026-09-08)
now confirms v2 Hantro operation without the old reference warnings, pairing,
normal/error exit and reconnection. Native performance text was absent, motion
tore and some samples had audio roughness. `CONFIG+=gpuslow` defines `GL_IS_SLOW`;
direct DRM has no overlay implementation, and `DRM_FORCE_EGL=1` alone did not
establish EGL selection. Resolve the renderer/HUD and audio before selecting this
client or undertaking long acceptance. The historical host/baseline records below
retain their original scope.

## Current revision

The opt-in v5 statistics candidate adds `build-qt-egl.sh --stats`; the default
still selects v4 and refuses to overwrite a retained executable. It reuses the
existing video counters once per second and emits only the fixed numeric
`streamstats.h` schema when `R46H_STREAM_STATS=1` and stdout is a pipe. Pipe writes
are bounded/nonblocking; a full or closed diagnostic consumer does not stop the
stream. Decoder probing never enables this output. Native overlay, decoder,
audio-buffer and input policies remain unchanged.

The report includes received/decoded/rendered FPS, network/pacing drops, decode
and frame-queue time, rendering-call duration, RTT, host processing time and
pending network-audio duration. Rendering-call duration is not GPU execution
time; network-audio queue length is not device queue depth or speaker latency.
The focused native check exercises the actual formatter and pipe code with
controlled counters. Actual stream/Hantro/audio values remain a device gate.

V5's clean source is `0d44133a90ca2b4aa13e8094ac56cfa01d563eb2` on
`codex/r46h-moonlight-stats-v5`. `revision-v5/receipt.json` binds its header/patch,
build and checks. The 9,549,752-byte ELF has SHA-256
`7ef297e9589438922dcb60eb677590bbb0a96fcdf174903f5a0e634ddedde5b9`.
Existing SPS/quit, fresh-list, unreachable-pairing and EGL-preference checks passed.

V4 applies [qt-listapps.patch](qt-listapps.patch) to the retained v2 source with
the same EGL build preference as v3. The upstream monitor announces an online
host before fetching its app list; the old CLI printed that cached list on the
notification. V4 uses the existing NvHTTP getAppList request after pairing and
copies address/port/certificate under the existing computer lock. The original
certificate checks and HTTP timeout remain in NvHTTP; no second transport is added.

The focused test executes the actual found-computer branch. The old branch fails
on an empty cache; the fixed branch passes fresh/stale/empty/failed/unpaired and
duplicate-event cases. Build through a clean committed source tree with
[build-qt-egl.sh](build-qt-egl.sh); outputs go to `revision-v4/`. Device retrieval,
video/audio and return remain untested for this new binary. Keep v3 and Embedded.
The clean-source build is commit `4672b9f0bcd3fead08540f8c212ed150f69c509b`;
`revision-v4/receipt.json` records the recipe/patch hashes and checks. The ELF is
9,549,704 bytes, SHA-256
`352123d4c2be72f1678224748a36d8ca4fe13fa8f8083518f311bebc36a5d526`.

### Retained v3 build and result

The retained v3 recipe built the frozen v2 source with
`CONFIG+=vkslow`, removing `GL_IS_SLOW` while keeping Vulkan deprioritized.
The [2026-09-09 session](../gaming-shell/STREAMING.md#attended-result-2026-09-09)
confirmed native performance text, normal short A/V, exit, host-loss return and
reconnection on R46H. Exact final renderer class was not retained in the log.
There is no new source or audio patch. The build checks `HAVE_EGL`, `HAVE_DRM`,
`VULKAN_IS_SLOW` and the absence of `GL_IS_SLOW`; existing SPS/quit/CLI tests and
unreachable pairing pass. This changes renderer preference, not proof that EGL
will import Hantro frames or display the HUD on R46H.

The v3 binary and receipt are in
`mainline/out/.cache/r46h-moonlight-qt/revision-v3/`; executable SHA-256 is
`9d61bd84569adf7f13309f693c89cfbb0fe63bad5e26c0700471af71e52c0b90`.
Use the shell's `build-streaming.sh` with that binary/hash for the combined
experiment. The current combined package is frozen alongside the device-settings
receipt. Keep v2 and the accepted Embedded path for comparison/recovery.

### Retained decoder, pairing and input changes

[qt-r46h.patch](qt-r46h.patch) changes four upstream files: preserve H.264 SPS
metadata on the DRM/V4L2 Request path, quit on a fresh L1 + R1 press even with
another button held, and return status 1 from CLI launch/stream failures instead
of waiting for a dialog. CLI launch refuses to terminate a different host app.
Regular GUI error dialogs and other decoder paths retain their previous policy.
The existing main-loop shutdown still waits for deferred connection cleanup.

Revision 2 adds [qt-pairing.patch](qt-pairing.patch) after that patch: CLI
pairing exits 0 on success/already-paired identity and 1 on failure, without
requiring an invisible dialog. An isolated complete ARM64 client returned 1
after the ten-second unreachable-host pair check. Actual pairing against the
isolated Mac Sunshine and a subsequent already-paired invocation both exited 0
without acknowledgement; these were ARM-container checks, not R46H tests. The new
[desktop management runbook](../gaming-shell/STREAMING.md) owns PIN privacy,
host settings and its direct display supervisor. Runtime libraries and the
accepted v1 decoder/input patch are unchanged. The revision 2 source/binary
and checks are frozen in `revision-v2/receipt.json`; v1 remains retained below.

The build reuses upstream v6.1.0 and the release-era packaging recipe at
`a31bfbf626c2f35903a69fab210c024da032f2da`. The pinned ARM64 builder is
`cgutman/moonlight-packaging@sha256:f25a3e2ad90b85d1a4358e2d612ed311165cddd62aa194455a5dbed844d66d69`.
It supplies Qt 6.8.2, SDL 2.33.0 and libavcodec 61.19.100 with V4L2 Request.
The v1/v2 command was `qmake6 PREFIX=/usr CONFIG+=gpuslow /src/moonlight-qt.pro`, then
`make -j4 release` in an external output directory. Strip only the staged binary.
Sources and the patch are pinned; no official-package byte reproduction or
two-build determinism claim is made.

### Quiet A/V comparison reference

[make-av-test.py](make-av-test.py) generates a 12-second 640×480/60 video and
matching 48 kHz stereo PCM, with quiet 100 ms cues at 1/3/5/7/9/11 seconds and
5 ms fades. It never starts playback. The generated WAV/MKV and hashes are under
`mainline/out/.cache/r46h-unattended-20260909/av-reference/`.
Play the same waveform locally and through Sunshine at the accepted mixer level,
capture actual ALSA period/buffer/queue data, and ask the operator about pops and
cue alignment. This separates local output from stream behavior without changing
gain or guessing a driver cause. Automated PCM/frame checks are not audible proof.

The retained `revision-v1/receipt.json` owns v1 inputs, checks and artifact hashes.
`moonlight-qt-r46h-v1.tar.gz` is 23,550,123 bytes, SHA-256
`23884b64c92c1e562414b2654c7072ebd1f91463d48d9fbbb50da19c80813721`.
It differs from the baseline only in the executable and two provenance documents.
The frozen patched source is `moonlight-qt-r46h-source.tar.gz`; the accepted
runtime libraries, wrapper, global input, audio and display code are unchanged.

Host checks passed:

- [The focused check](../tests/test-moonlight-qt-patch.py) compiles the actual
  decoder/quit predicates and `writeBuffer()`, and executes the actual QML
  handlers in QJSEngine. It covers single shoulders, both shoulders with another
  button held, release events, the quit-disable option, CLI failures/normal exit
  and the preserved GUI error path. This is not SDL event delivery or LCD proof.
- Artificial VideoToolbox H.264 advertises six references. The old SPS rewrite
  produced 121 warnings and changed 114 of 120 software-decoded frame hashes.
  The candidate preserved input bytes, with zero warnings and all frame hashes
  matching. This isolates the host hypothesis; Hantro still needs a changed run.
- The complete packaged program loaded Qt/QML offscreen and returned status 1
  after the native 30-second unreachable-host deadline, without acknowledgement.
- All 104 ELF files resolve through the same 102 system-library paths as before;
  provider versions match the retained v0.17 package status. No runtime dependency
  was added. Private probe state and the build container were removed.

Next: stage the current [run-stream.sh](run-stream.sh) and invoke
`run-stream.sh --qt HOST BINARY_SHA256` using the revision receipt's executable
hash. It checks identity, private paired state, binary and dependencies before
stopping ES-DE, then uses the shared transient cgroup with a 120-second deadline
and ten-second cleanup limit. The backend/environment/hash/refusal/recovery checks
pass on the host; this launcher revision is not physically tested. First confirm warning-free Hantro decoding and
attended LCD/colors/HUD/audio, then test individual shoulders, L1 + R1, host loss
and connection failure with visible ES-DE recovery. Keep the software fallback.

## Official baseline artifact

The official ARM64 Debian package is Moonlight Qt **6.1.0-4**, obtained from
the repository linked by the [upstream SBC guide](https://github.com/moonlight-stream/moonlight-docs/wiki/Installing-Moonlight-Qt-on-ARM%E2%80%90based-Single-Board-Computers).
Its 3,372,940-byte `.deb` SHA-256 is
`82a20826550d5c2f8e63ac55930894c95f75a6b4015f2b1397ca287fa0d6a727`.
APT verified repository metadata and package hashes. Debian dependencies come
from the existing builder's `20260713T000000Z` snapshot.

The external cache `mainline/out/.cache/r46h-moonlight-qt/` retains packages,
metadata, source review and `receipt.json`. Expanded staging and the audit
container were removed after archive verification. The public transfer tar
is `moonlight-qt-candidate.tar.gz`, 23,546,352 bytes, SHA-256
`3e69df3e147c2106aa9f74988bfc0339326ade62793d4ca5c412d3f150178ae8`.
It contains only `usr/` and [qt-client.sh](qt-client.sh), including licenses.
No private state, APT configuration or install scripts are applied to R46H.

The dependency simulation used `/var/lib/dpkg/status` extracted read-only from
the retained v0.17 image and checked its consolidated receipt against the
accepted device identity. It needs 32 new packages, including the explicit
`qt6-qpa-plugins` console/offscreen plugins, with zero upgrades/removals. The
extracted payload uses about 67.5 MB of file content.

All 104 ELF files are ARM64. Their dependency audit found no missing libraries;
102 system-library paths map to packages installed at the same versions in the
v0.17 image. Target `ldd`, startup and ark's media/DRM read/write permissions
also passed. `libproxy` keeps a private library in its own subdirectory, which
the wrapper includes in `LD_LIBRARY_PATH`.

## What host checks establish

- `--help`, `stream --help`, `pair --help` and the packaged wrapper run in an
  ARM64 container. The focused wrapper check covers private state, paths with
  spaces, argument forwarding and exit status.
- An eight-second offscreen Qt/QML startup loaded the application and ended at
  its deadline. It logged one QML ToolTip warning and expected decoder/renderer
  failures because the container has no display/VPU. This is not rendering or
  hardware-decoding proof.
- The official binary includes `h264_v4l2request` and Request API routines;
  `--video-decoder hardware` and `--performance-overlay` are available. Decoder
  code presence alone does not prove compatibility with R46H's Hantro driver.
- Reviewed files match upstream v6.1.0 Git blobs at
  `f786e94c7b2f943e24e65d7d74deb539b827fc84`. The package ships SDL 2.33.0 and
  bundled codec code. Its hashes identify the official package; no local
  source-build reproducibility claim is made.

Qt's native audio renderer requests float PCM and derives its buffer from the
negotiated Opus frame size. Do not assume the Embedded client's
`SDL_AUDIO_SAMPLES=1024` setting controls it. Measure actual ALSA period/buffer,
queue delay and A/V behavior during the candidate run.

The unmodified baseline uses Start + Select + L1 + R1 to quit. The accepted
Embedded client keeps L1 + R1; the revision ports that chord, pending device proof.

## Official baseline R46H result (2026-09-06)

The unchanged v0.17 card cold-booted through the 1500000 → 115200 UART switch.
The hash-verified package ran entirely from private tmpfs without installation.
Offscreen pairing established the identity used by the real stream, but its Qt
UI stayed open until the 60-second deadline; pair exit 124 is not a pair failure.

Two 120-second launcher envelopes used the patched Mac Sunshine. The second
added process/PCM sampling; stopping the owned host at client time 69 seconds
released native video statistics. H.264 used `h264_v4l2request`, `hantro-vpu`
and the DRM renderer. Live process descriptors included `/dev/video1`,
`/dev/media0` and the display card; decoded and rendered frames advanced.

| Measured second sample | Result |
| --- | --- |
| Incoming / decoded / rendered FPS | 60.02 / 60.02 / 59.60 |
| Network drops / jitter drops | 0.00% / 0.71% |
| Average decode / frame queue / render time | 3.52 / 2.66 / 16.11 ms |
| Process CPU, one-core scale, nine active intervals | 40.5–42.1%, median 40.9% |
| SoC temperature, ten active samples | 59.5–63.8 °C |
| Actual ALSA period / buffer | 1440 / 2880 frames, stereo S32_LE at 48 kHz |
| Sampled sound-device queue | 31.7–53.8 ms |

The earlier Embedded sample's median CPU was about 98%; these are separate
short runs, not a controlled thermal or end-to-end latency comparison. LCD
motion, readable HUD, audible output and perceived A/V timing remain unconfirmed.

Both runs logged repeated `number of reference frames ... exceeds max (1)`
warnings (6654 / 3577). The reviewed Qt `FFmpegVideoDecoder::writeBuffer()`
forces SPS reference count and buffering to one, and runtime logs confirm that
fixup is active. This is a concrete compatibility hypothesis, not a verified
fix. The revision above establishes the host comparison, pending R46H retest.
Startup also logged Qt/SDL DRM handoff warnings and missing plane
color properties; advancing frames do not prove correct LCD colors.

Both deadlines returned 124 with mixer/frontend restoration status zero. Host
loss released the stream but left Qt's error UI open until the deadline: automatic
product return to ES-DE is not implemented. Native four-button exit remains
unchanged. Port L1 + R1 and resolve these paths before selecting Qt for integration.
Frontend/input/volume services ended active with zero restarts; ext4 and matched
kernel faults were zero, and `/roms` stayed read-only. The initial fault regex
matched the word `Default`; a word-boundary check corrected that false positive.
Serial confirmed filesystem detach and poweroff. Private state and owned servers
were removed; no host service, rootfs rewrite or global input change was applied.

Evidence and `receipt.json` live under the cache's `attended-20260906144320/`.
Its 41,532-byte `device-evidence.tgz` was verified against the UART SHA-256:
`485ce95e92de9166077658370324911bb30044af81abc1e358f624e94e919d4d`.
Logs omit request parameters and private state; the retained launcher identifies
the exact runtime settings. Keep Embedded as fallback while these gates are open.

## Bounded procedure for changed candidates

1. Rediscover serial/network nodes and verify the current v0.17 identity,
   storage and services. Do not rewrite BOOT/rootfs or change global input.
2. Extract the hash-verified public tar into a new task-owned
   `/run/r46h-moonlight-qt-test`, then restore that directory to `ark:0700`.
   The wrapper puts credentials/cache under its sibling private `state/`.
   Do not publish, archive or log that directory.
3. Check target dynamic libraries, Qt EGLFS/KMS plugins, readable Hantro/media
   nodes and the accepted display/input permissions before stopping ES-DE.
   Use the same patched Mac Sunshine and isolated host state as the accepted
   run. Pair through `qt-client.sh pair HOST --pin PIN` with a private output
   file. Remove all request-parameter lines and the PIN before captured output;
   Qt logs pairing material in URLs. Do not retain raw pairing logs or commands.
4. Use the canonical `run-stream.sh --qt HOST BINARY_SHA256` above. Frozen
   receipt launchers remain historical evidence: they predate corrected argv
   guards and transient cgroup cleanup. The current Qt branch keeps the accepted
   mapping and selects the combined gamepad, EGLFS/KMSDRM, native ALSA, H.264 at
   640×480/60, 4 Mbps, hardware decoding and the native HUD. It does not apply
   Embedded's audio-buffer variable or terminate the host app on client exit.
5. Require actual Hantro/media device use and advancing decoded/presented
   frames. Record decoder/renderer names, CPU, temperature, PCM and health.
   Confirm LCD motion/audio with the operator. A software fallback or a menu
   alone is not a hardware-decoder pass. If initialization fails, preserve its
   logs and isolate the failing interface before another attempt.
6. Restore the mixer and ES-DE, capture health, retain public evidence, remove
   target/host private test state, stop owned services and power off through
   serial. Choose the client only after this result.

Host regression:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 mainline/tests/test-moonlight-qt-client.py
sh -n mainline/gaming-moonlight/qt-client.sh
PYTHONDONTWRITEBYTECODE=1 python3 mainline/tests/test-project-docs.py
git diff --check
```
