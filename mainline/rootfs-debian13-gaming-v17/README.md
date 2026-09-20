# R46H Debian 13 gaming p2 v0.17

Status: **HOST + P2 MEDIA + DEVICE INFRA + STICK SMOKE PASS / SAVE MENU FAIL / PSP DEFERRED**

This is the narrow ES-DE configuration successor to exact p2 v0.16. ES-DE
merges a custom `es_systems.xml` with its bundled systems unless the custom file
has a root-level `<loadExclusive/>`; therefore v0.16 still advertised bundled
Dreamcast despite omitting it from the custom 13-system list. V0.17 adds that
marker and keeps the 13-system list exclusive.

The target-proven 10 ms remote-input binary, emulator cores, ROM and media
links, settings, services, and Dreamcast diagnostic core/content are retained
byte-exactly. The builder replaces five identity-bound configuration/helper
files plus two receipts and changes only the p2 filesystem UUID/label. BOOT, p1
and p3 stay outside the image and any later write plan.

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v17.py validate-inputs
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v17.py build
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v17.py validate
```

The offline composer writes no block device and uses the exact published v0.16
image as its only filesystem base. Input hashes, bounded debugfs changes,
filesystem identity, receipts, retained files and a clean ext4 image are checked
inside the pinned container and again independently.

For a future required write, independently hash the target p2 and generate only
the fixed-profile p2 operation with `generate-debian13-write-plan.py --artifact-id
debian13-p2-gaming-v0.17 --profile-id hl-r46h-v22-g92-62534975488-v1` and run
it through the session-scoped Card Agent. Never reuse a prior `/dev/diskN`.
The current card has already passed the media gate below; proceed to persistent
device acceptance with that image.

Two builds from source commit
`221075dc4f7bf0b7977e52f6764523118f2fd982` were byte-identical, followed by
a separate post-publish validation:

- image SHA-256: `efccaf9b1d6b48624427f96f0d995c0143cb50e3447f31506ef6553973538897`
- `BUILD-INFO` SHA-256: `45c7c732d36b8fb6ee5b33232ae69041e6159b285b667ab7eba2a81f34a9947e`
- consolidated receipt SHA-256: `67ed46759d1345fd5189e503376a63ce2d0f8082d705ea8059198858f0fcd1c2`

## Device evidence that motivated the successor

Exact p2 v0.16 passed cold boot, base smoke, SDR104/150 MHz, read-only `/roms`,
the 10 ms single-step roundtrip, and ES-DE/Game Gear screenshots. It failed its
product gate when ES-DE logged 14 loaded systems and exposed Dreamcast from the
bundled configuration.

A temporary read-only bind candidate added only `<loadExclusive/>`. ES-DE then
logged 13 parsed/loaded custom systems, no bundled systems and no Dreamcast;
guarded ES-DE, Game Gear and PPSSPP (`comm=Main`) screenshots passed. The binds
were removed, exact v0.16 hashes restored, health stayed clean and the R46H was
powered off normally.

## Persistent media evidence

On 2026-09-05 the fixed-profile card passed a guarded p2-only deployment:

- Audit session `session-20260905T074249Z-44323-78e9fb79-f1fa-472f-8aba-4fe812a6755b`
  verified identity, geometry, all-unmounted state and card-prefix SHA-256
  `3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`.
  Its complete write-before p2 clone and a separate raw read both matched
  `985e078a532d5b22b7f351158dd6e462ff8ea54a6d2647507b226b21e6c27171`.
- Write-plan SHA-256
  `e39664d988bcaa38aead36ffd0fbea0fe7fe3debe9d576d5068fd24b690bfca7`
  bound that write-before hash, artifact and fixed profile. Deploy session
  `session-20260905T075203Z-45037-f92e4536-49c7-4c73-a544-17058e944d17`
  wrote exactly 10,716,877,312 p2 bytes. Its transaction readback and a second
  independent raw read both matched the published image SHA-256 above.
- The card-prefix hash stayed unchanged, p1 and p3 remained unmounted and
  outside the operation, and macOS safely ejected the card. The rollback clone
  and session receipts remain under `mainline/out/r46h-card-agent-sessions/`.

## Persistent device evidence

Media proof does not establish R46H behavior; the observations below are
separate device evidence.

The 2026-09-05 serial-first cold boot used the written v0.17 p2. Its UUID,
consolidated receipt and installed identity-bound helpers matched; base smoke,
Panfrost FBO, SDR104/150 MHz, zero ext4 errors and read-only `/roms` passed.
ES-DE logged the exclusive custom file and exactly 13 parsed/loaded systems.
Remote-input self-test passed; one right step reached CPS1 and one left step
returned the byte-identical initial frame. Captures used serial transport;
Wi-Fi remained disconnected and strict SSH was not tested.

The operator launched Game Gear `020.zip` (Fatal Fury Special) and `001.zip`
(James Bond 007), reporting no problem in either sample. Valid Ozone and 007
gameplay PNGs were fetched, verified and removed from the device. One PCM XRUN
sample coincided with the captured Ozone pause menu; later active gameplay was
RUNNING, all three product services stayed active with zero restarts, and no
kernel storage/GPU fault appeared. This does not establish sustained pacing.

The operator also confirmed that 007's Ozone menu has no save-state entries;
save/load acceptance failed at the missing entry. Installed Genesis Plus GX metadata
declares save support, but its binary lives outside configured
`libretro_directory`; the same discovery gap affects the other custom cores.
RetroArch 1.20 [builds core information from that directory and gates save menus
on it](https://github.com/libretro/RetroArch/blob/v1.20.0/core_info.c).
This is a source-supported cause awaiting a bounded device comparison; no
runtime configuration was changed. Save/load and gameplay progress after reboot
remain unverified; merely retaining SRAM files is insufficient.

PSP `psp/我的世界PSP/我的世界PSP.PBP` launched through ES-DE with `comm=Main`;
the anchored screenshot guard passed and a validated PNG showed gameplay.
PCM was RUNNING, services had no restart and no storage/GPU fault appeared.
The operator initially reported only rightward left-stick response, while
unsure of this game's controls. Earlier center-near capture windows were not
sufficiently synchronized to localize it. A later 300-second virtual capture
recorded X 110–999 and Y 74–937, returning to 515/504 with no `SYN_DROPPED`;
a live raw/virtual snapshot agreed at X 979/981. The unchanged hardware smoke
core then ran with the accepted RetroArch config. The operator explicitly
confirmed both sticks' four directions, polarity and return to center were
normal. The helper exited with `result=pass`, restored the mixer and returned
to ES-DE; all three product services had zero restarts. No input mapping was
changed. PSP-specific behavior remains unaccepted and was explicitly deferred
by the user in favor of PC game streaming.

This second session joined an already running device at 115200; its initial
1500000 listener saw no boot bytes, so it adds no cold-boot proof. Identity,
base/GPU/storage checks passed, and the event/smoke logs were retained and
hash-verified under `mainline/out/.cache/r46h-v17-attended/` before tmpfs cleanup.

The preceding warm reboot passed identity/helper hashes, base smoke, storage audit,
read-only `/roms`, actual 13-system loading and an ES-DE screenshot matching the
initial frame. Product services had zero restarts; volume remained 201. The two
generated Game Gear SRAM files retained their bytes, but no game progress was
restored. Final health passed, all task exports were removed, and `sync` plus
controlled poweroff ended with serial-confirmed filesystem detach and
`Powering off.`. The subsequent attended session resumed the same card; its
[streaming record](../../docs/GAME-STREAMING.md) owns the later test and final cleanup.

Raw serial and validated PNG evidence are retained under
`mainline/out/.cache/r46h-v17-physical/`; the capture is
`serial/cold-boot-20260905T085820Z.log`, and `events/` contains the bounded
stick captures. These results do not establish complete product acceptance,
launcher LCD motion, strict SSH pairing or statistical boot reliability.

## Persistent device acceptance

The infrastructure and dual-stick smoke portions passed above. Save discovery
remains open; PSP-specific investigation is deferred. The active next stage is
[Game Streaming](../../docs/GAME-STREAMING.md). Repeat accepted checks only after a
relevant change. For a future changed candidate, follow the
[serial procedure](../../docs/DEVELOPMENT.md#serial-and-physical-sessions)
before cold power-on, then:

1. Check the v0.17 p2 UUID and consolidated receipt against the builder's
   identity, the selected kernel, installed `r46h-rootfs-smoke` and
   `r46h-storage-audit`, SDR104/150 MHz and read-only `/roms`.
2. Check ES-DE's actual startup log: exactly 13 loaded custom systems and no
   bundled Dreamcast. Counting entries in the custom XML alone missed v0.16's
   failure and is insufficient.
3. Check the 10 ms single-step roundtrip and guarded ES-DE/Game Gear/PPSSPP
   frames. For strict SSH, first configure Wi-Fi without logging credentials,
   verify the new host key over serial and pair the restricted public key.
   **Pairing preparation is open:** the repository's newest
   [pairing helper](../rootfs-debian13-gaming-v10/pair-remote-key.sh) rejects
   every UUID except p2 v0.10. Prepare a reviewed v0.17-bound helper before the
   SSH gate; do not bypass its identity checks or treat serial captures as SSH
   transport proof. Serial boot/storage checks can proceed independently.
4. Compare health and service restarts before/after the samples and a warm
   reboot. Abort on new MMC/ext4 faults, persistent GPU faults or XRUNs; retain
   evidence and restore temporary state. Finish with `sync`, controlled
   poweroff and serial confirmation.

Keep operator LCD motion, audible output, physical controls and save/reboot
observations in one attended batch. Machine captures and running PCM leave
those claims open. Current priorities remain in
[Project Context](../../docs/PROJECT-CONTEXT.md#immediate-next-work).
