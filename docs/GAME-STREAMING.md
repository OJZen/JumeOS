# R46H game streaming

The next stage receives a Sunshine game stream on R46H through Moonlight.
The Mac remains the accepted A/V host. A temporary Linux host in its Docker VM now
has real protocol/input loopback proof; Windows remains an alternative. This is a
temporary integration experiment, not a new card release.
The [ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md) owns accepted hardware
evidence; the [current context](PROJECT-CONTEXT.md) owns project priority.

## Scope

- The user chose the current Mac as server and explicitly requested Sunshine
  as a manually started test tool: no system service or startup registration.
- Official Sunshine `v2026.516.143833` for Apple Silicon was downloaded,
  checked against the release's SHA-256 and extracted to the external cache.
  Its App signature validates. An absolute config path keeps test credentials,
  certificates, state and logs in that cache. UPnP is disabled.
- R46H connected to the operator's Wi-Fi and received the intended test
  server's `serverinfo` response, then paired successfully. The operator
  confirmed live picture and audible output. This does not establish strict SSH. Never copy Wi-Fi secrets into this document.
- Moonlight Embedded `v2.7.1` ran against Debian 13 at 640×480/60 FPS requested,
  H.264/4 Mbps, using SDL and software decoding. It reuses the accepted ES-DE SDL controller
  mapping. This is not proof of Hantro hardware decoding.
- Test artifacts and receipts live in `mainline/out/.cache/r46h-streaming/`.
  Rediscover host/device addresses each session rather than hardcoding them
  into a product launcher.

The [client runbook](../mainline/gaming-moonlight/README.md) owns the build,
FPS/CPU overlay, L1 + R1 exit patch and bounded test launcher.

## Open audio observation

During streaming, the operator reported occasional faint speaker pops; earlier
local-game tests did not make them obvious. Cause is **unknown**: this report
does not isolate the driver, audio route, client buffers, network or host capture.
Compare matched local/streamed audio at the same accepted volume and correlate
PCM/XRUN and stream logs before changing audio policy. Do not raise speaker gain.

## Accepted test and retained evidence (2026-09-05)

The operator confirmed live Mac picture/audio, visible FPS/CPU values and the
simplified exit. The L1 + R1 run ended with client status 0, restored the accepted
mixer and returned to ES-DE. Individual shoulder-button behavior was not
separately observed. The patch compiled for arm64 and passed the deterministic
HUD/SDL check; the 12 focused documentation/rootfs checks also passed.

A logged original-server sample produced 99 HUD readings: **29–32 FPS, CPU 94–131% of
one core**, with 3030 client-reported frame-number gaps. Requested 60 FPS is not
achieved in that sample. The subsequent [cadence analysis](../mainline/gaming-moonlight/README.md#frame-cadence-analysis)
reproduced frame halving from Sunshine's H.264 reference-buffer setting.
The separate CLI quit attempt did not stop that sample;
shutting down the owned host process ended it, with wrapper restoration status 0.
That host-stop path logged a connection termination and is not graceful-protocol proof.

The final frontend/input/volume services were active with zero restarts; ext4
errors and matched kernel faults were zero, and `/roms` remained read-only.
Sunshine and the transfer server stopped. Target tmpfs state and expired test
keys were removed; serial confirmed filesystem detach and `Powering off.`.
No service/startup registration or rootfs image rewrite was performed.

Retained under `mainline/out/.cache/r46h-streaming/`:

- `receipt-20260905.json` owns source/artifact identities and evidence hashes.
- `moonlight-hud.tar.gz`: 328952 bytes, SHA-256
  `6f97c1e33dab8e70d34e422b7ae86845bd70f829b091929816d0332f0f9b44ce`.
- `evidence/device-20260905.tgz`: target logs/health/build package list, checked
  against the UART-provided SHA-256 before tmpfs cleanup; no keys included.
- `evidence/performance.json`, `evidence/sunshine-console.log` and
  `moonlight-hud-build.log` retain the sample and host/build evidence.

The serial/poweroff trace is
`mainline/out/.cache/r46h-v17-attended/serial/running-20260905T1038Z.log`;
that directory's `SHA256SUMS` also covers the accepted stick/smoke evidence.

## Corrected host and audio comparison

The same client/settings against the patched Sunshine host produced 257 HUD
samples: **55–61 FPS, median 60; CPU 89–130%, median 97% of one core**. No
frame-gap messages were logged. The operator accepted picture/audio, then
confirmed L1 + R1. Client and restoration status were zero. A temporary black
screen preceded ES-DE recovery without intervention; duration was not measured.

The operator then reported audio lagging video. The
[audio comparison](../mainline/gaming-moonlight/README.md#audio-buffer-comparison)
owns the measured PCM queue and isolated 1024-sample candidate. It changes only
the client audio period; host, video settings and mixer remain the same.
The five-minute run retained median 60 FPS with no frame-gap or audio-error
messages, and reduced sound-device queue time to about 42 ms. Subjective A/V
comparison passed on the attended repeat: the operator heard no problematic
delay or pops, then confirmed exit. This short sample does not close long-run
pop coverage or measure end-to-end latency. Timeout in the first run restored
mixer/frontend; final health and
serial poweroff passed. Current receipts/logs are under
`mainline/out/.cache/r46h-streaming/candidate-attended/` and the repeat's
`candidate-audio-listen/`; temporary keys and
servers were cleaned up.

## Next gate

The [2026-09-09 v3 session](../mainline/gaming-shell/STREAMING.md#attended-result-2026-09-09)
passed native HUD visibility, short default-preset picture/audio, shoulder exit,
host-loss return and reconnection. Its Hantro descriptors and 59.25 rendered FPS
sample are recorded separately from the operator observations. Higher-preset and
long-session v3 results remain open; prior v2 audio/tearing observations are retained.

1. Test the [v5 client](../mainline/gaming-moonlight/QT-CANDIDATE.md), including v4's fresh application-list fix, on R46H. Actual Sunshine pairing/list/video/input now pass the isolated [Linux host check](../mainline/gaming-stream-input-test/README.md#automated-protocol-check); target host management remains open.
   Keep the known-name fallback and current remote UI tool. Preserve the accepted
   Embedded/ES-DE path while extending the v3 acceptance boundary.
2. Follow the [shared-display gate](DEVICE-SHELL.md#display-and-input-decision)
   before integrating streaming with the new desktop/global panel. Verify actual
   Moonlight under Wayland, Hantro use, colors, A/V and input handoff. Two Qt
   windows or local endpoint actions do not establish this path.
3. Close real input using the [temporary Linux test host](../mainline/gaming-stream-input-test/README.md) on the current Mac, or the Windows fallback page.
   The user accepts controlling this program through the stream as the first input
   milestone. Verify LAN access, both sticks, buttons,
   triggers and feedback on the handheld. Real-game compatibility remains a later gate.
   Keep Sunshine manually started with isolated state. Select the product client
   and persistent pairing only after the management experiment passes.
   Keep ES-DE recovery until the desktop's launch/exit/crash
   lifecycle is accepted. Product sessions should not inherit the experiment
   deadline; restart/reconnect must work without unnecessary re-pairing.
4. Once those paths exist, run one attended 30-minute game session and three
   launch/exit cycles. Record A/V, CPU, temperature, frame gaps and audio errors;
   observe single shoulder buttons, L1 + R1, return-screen delay and reconnect.
   This closes a bounded stability sample, not statistical reliability.

The accepted Embedded buffer is a separate fallback; its audio acceptance does
not cover Qt's native ALSA path. Preserve BOOT, p3, emulator bytes and global input mappings.
Use the bounded launcher, health checks and cleanup for each changed sample.

The official [macOS Sunshine documentation](https://docs.lizardbyte.dev/projects/sunshine/latest/md_docs_2getting__started.html)
states that native macOS virtual gamepads are unsupported. The isolated Linux
test host supplies its own virtual controller inside the VM; it neither adds a
Mac input driver nor proves input in native Mac games. R46H-to-LAN delivery remains open.

The existing [Hantro probe](../mainline/bringup-tests/HANTRO-CODEC-DECODE-PROBE.md)
proved pinned H.264/VP8 fixtures, including exact reference-frame paths. It did
not prove arbitrary real-time Sunshine streams. Moonlight Embedded's Rockchip
backend is not automatically compatible with this mainline V4L2 Request stack;
choose an existing compatible decoder path before considering custom code.
