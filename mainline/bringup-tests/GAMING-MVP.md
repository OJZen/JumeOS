# R46H Debian-native gaming MVP

> Historical v0.3 bring-up runbook. The current product uses GLES2, read-only
> `/roms` mount ordering and system-level volume keys; see
> [GAMING-PRODUCT.md](GAMING-PRODUCT.md). Software-renderer and `20,20` passages
> below describe old diagnostic evidence, not the current frontend policy.

This is the shortest path from the accepted Debian 13 base to a visible,
interactive emulator loop. It does not rewrite the TF card, repartition media,
replace active `boot.ini`, or rebuild the 10.7 GB root image.

The current v0.3 payload reuses the accepted persistent kernel
`6.12.99-r46h-mainline-v0.10-adc-full-range` and its matching module tree.
That kernel has passed boot, Panfrost, ADC input, RK817 audio, passive Wi-Fi and
Hantro gates. The later v0.12 change only corrects the charger termination
property and is unrelated to starting RetroArch, so v0.12 persistence is not
on this critical path.

The payload installs Debian 13's native arm64 RetroArch 1.20 packages and four
native libretro cores. It does not reuse the old ArkOS EmulationStation binary,
which directly depends on `libMali.so`, or the old RetroArch binary, which is
bound to obsolete FFmpeg and RGA ABIs. The first automatic frontend is native
RetroArch RGUI; EmulationStation integration remains a later UX phase.

## Build

Commit the source scope, then build and validate from the external workspace:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-gaming-mvp.py build
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-gaming-mvp.py validate
```

The builder uses the pinned, previously accepted Debian v0.1 arm64 container,
downloads only packages absent from that exact base, compiles a small arm64
libretro diagnostic core, installs the complete offline package set in a
network-disabled validation container, checks RetroArch KMS/EGL/GLES/ALSA/UDEV
features, loads the diagnostic core with null output, and publishes one
immutable tar archive. Private source, Docker export and integration work stays
below `mainline/out/.cache/r46h-gaming-mvp-build` and is removed on success or
failure.

## Install or upgrade v0.3

The preferred positive path is a read-only HTTP transfer over the already
accepted Wi-Fi connection. Download the generated
`r46h-gaming-mvp-v0.3.tar.gz` to `/var/tmp`, compare it with the exact SHA-256
printed by the builder, then extract into one root-only directory on p2. A
read-only USB source remains an equivalent fallback. Do not copy the archive
into `/run`: the accepted rootfs gives `/run` a smaller tmpfs, and that path
previously failed with `No space left on device`.

The installer deliberately requires its payload at
`/run/r46h-gaming-mvp-v0.3`, so expose the verified persistent staging tree
there with a bind mount only for the installation:

```sh
printf '%s  %s\n' ARCHIVE_SHA256 /var/tmp/r46h-gaming-mvp-v0.3.tar.gz |
  sudo sha256sum -c -
sudo test ! -e /var/lib/r46h/.gaming-mvp-stage-v0.3
sudo install -d -o root -g root -m 0700 /var/lib/r46h/.gaming-mvp-stage-v0.3
sudo tar --no-same-owner -xzf \
  /var/tmp/r46h-gaming-mvp-v0.3.tar.gz \
  -C /var/lib/r46h/.gaming-mvp-stage-v0.3
sudo chown -R root:root /var/lib/r46h/.gaming-mvp-stage-v0.3
sudo chmod 0700 /var/lib/r46h/.gaming-mvp-stage-v0.3
sudo install -d -o root -g root -m 0700 /run/r46h-gaming-mvp-v0.3
sudo mount --bind \
  /var/lib/r46h/.gaming-mvp-stage-v0.3/r46h-gaming-mvp-v0.3 \
  /run/r46h-gaming-mvp-v0.3
sudo /bin/bash /run/r46h-gaming-mvp-v0.3/install.sh
sudo umount /run/r46h-gaming-mvp-v0.3
sudo rm -rf -- /var/lib/r46h/.gaming-mvp-stage-v0.3 \
  /var/tmp/r46h-gaming-mvp-v0.3.tar.gz
sudo rmdir /run/r46h-gaming-mvp-v0.3
```

The installer requires the persistent v0.10 kernel, the exact Debian root
partition, zero ext4 errors, no failed unit and at least 1 GiB free space. It
points apt at a temporary empty source configuration, so every dependency must
come from the payload and no network repository can be contacted. It never
opens BOOT or EASYROMS writable. It installs and enables
`r46h-gaming-frontend.service`, but the service cannot start until the final
root-owned v0.3 receipt is published.

On the next ordinary boot the service starts RGUI on tty2. Quitting RetroArch
returns to tty1; it does not restart in a loop. The service condition skips
cleanly on the v0.8 fallback instead of creating a failed unit. Disable or
re-enable automatic startup explicitly with:

```sh
sudo systemctl disable --now r46h-gaming-frontend.service
sudo systemctl enable r46h-gaming-frontend.service
```

## Historical first v0.10 run

Reboot with CH340 capture, interrupt the exact U-Boot prompt, and reuse the
already accepted inactive v0.10 BOOT candidate:

```text
mmc dev 1
load mmc 1:1 0x02000000 boot.ini.v0.10-adc-full-range
if itest ${filesize} -eq 0x580; then echo R46H_V10_SCRIPT_SIZE_PASS; else echo R46H_V10_SCRIPT_SIZE_FAIL; fi
source 0x02000000
```

Never run `source` after a size failure and never run `saveenv`. During the
original acceptance a normal reset returned to v0.8. Since 2026-08-16 the
already accepted v0.10 candidate is the active BOOT script; the byte-exact v0.8
candidate remains available for an explicit one-shot fallback.

After Debian reaches multi-user, start the diagnostic core from serial:

```sh
sudo r46h-game-ui smoke
```

The expected positive result is eight vertical colour bars, a blinking square,
directional movement when the D-pad is pressed, colour inversion on A, and a
440 Hz tone from the speaker. The attended runner uses RetroArch's SDL2 software
renderer and a deliberately low RK817 volume (`20,20`). This is a
measured compatibility fallback: Debian RetroArch 1.20 reaches the Mali-G31
through SDL/OpenGL but its stock desktop GLSL shader does not compile on the
board's GLES 3.1 context. Panfrost remains independently covered by the
surfaceless GPU smoke gate; this first emulator loop proves display scanout,
ALSA and input without pretending that RetroArch's GL renderer passed.
`Ctrl-C` on serial terminates the dedicated RetroArch process group and proves
that it is empty before restoring the RK817 mixer controls and returning the
panel to tty1. This ordering matters: an earlier foreground-only prototype left
RetroArch alive after tty1 returned, so its tone started after the picture had
disappeared. A display, ALSA or input failure is treated as the next concrete
bring-up bug; it is not hidden by more media auditing.

The runner also proves that the unprivileged `ark` account can read both the
core and the fixed configuration before it changes the mixer or switches VTs.
A temporary root-only configuration once produced a misleading “picture works,
all buttons dead” result because RetroArch silently fell back to defaults; that
condition is now a preflight failure.

For this first loop, player 1 is deliberately bound to discovered udev Pad #0,
the separately exposed `gpio-keys` device. The attended v0.10 capture advertised
face buttons 304/305/307/308, shoulders 310..313, Select/Start 314/315 and
`BTN_DPAD_UP..RIGHT` 544..547. RetroArch's udev driver assigns these advertised
key codes ascending button numbers, so Select/Start are 8/9 and the D-pad is
10/11/12/13. The first sequential guess put Select/Start on Up/Down and mapped
physical Up/Down as virtual Left/Right; the observed horizontal-only movement
is therefore recorded as a mapping error, not a kernel input regression. The
smoke core intentionally has no B-button action; A inverts the colours. The two
ADC sticks are exposed by another event device and remain deferred; no
input-merging daemon is introduced on the critical path.

### Attended v0.10 result (2026-08-16)

The native loop reached the eight-bar smoke screen and produced the low-volume
tone through the built-in speaker. After the mapping correction, the operator
confirmed all four D-pad directions moved the square in the corresponding
direction and A toggled the colours. B remains deliberately unobservable in
this diagnostic core. Serial `Ctrl-C` then reported
`process_cleanup=pass`; independent postflight found zero RetroArch processes,
zero `/run/r46h-game-ui.*` sessions, mixer values restored to `201,201` and mux
`0`, ext4 `errors_count=0`, and zero failed systemd units. These checks close
the first display/audio/digital-input emulator loop. They do not validate
stereo separation, ADC-stick integration, arbitrary ROM compatibility or the
RetroArch OpenGL renderer.

The immediately following `r46h-game-ui menu` run also reached native RGUI.
The operator confirmed D-pad navigation, A to enter and B to return. Its serial
exit again reported `process_cleanup=pass`; postflight found zero RetroArch
processes, zero game sessions, restored mixer volume and zero failed units.
No menu setting was saved or changed.

Once the smoke core works, open the native RGUI menu:

```sh
sudo r46h-game-ui menu
```

The v0.2 payload also contains an original deterministic iNES/NROM test image,
not a downloaded or commercial ROM. Run it through Debian's real Nestopia core:

```sh
sudo r46h-game-ui nes-smoke
```

Expected output is a checkerboard with a movable square. The D-pad moves the
square and A changes its colour. This adds an actual emulator-core and ROM
execution proof to the frontend-only smoke results.

### Attended Nestopia result (2026-08-16)

Before publishing the v0.2 archive, the exact generated ROM bytes and candidate
runner were copied to root-owned `/run` paths for one non-persistent hardware
test. The ROM was 24,592 bytes with SHA-256
`f4e911f38aade8353853127e5e45b91aef1333061bdf865ec1775236e72abb0c`;
the Debian Nestopia core was
`250f0a134062aea0977b99861d20cba6e0a015835ef61ebf084566bcec92085f`.
On the exact v0.10 one-shot kernel, Nestopia displayed the generated
checkerboard and square. The operator confirmed all four D-pad directions and
A behaved as described. Serial `Ctrl-C` returned to tty1; postflight found zero
RetroArch processes, zero game sessions, restored mixer volume `201,201` and
mux `0`, ext4 `errors_count=0`, and zero failed systemd units.

This proves one real Debian libretro core can execute an original ROM and use
the accepted display/input path. It is not a broad game-compatibility claim.
The test used temporary `/run` files because v0.2 was not yet installed; those
paths disappeared on reboot. Persistent installation was completed later the
same day as recorded below.

### Persistent v0.10 and v0.2 result (2026-08-16)

The fast card's active `boot.ini` was changed from the accepted v0.8 script to
the already hardware-accepted v0.10 candidate. The active file was rehashed as
`915039bf17dea6aa2ba42701195510c346c70c8c81117151e7d153073fa1ceab`;
the retained v0.8 fallback remained byte-identical at
`cead3fbee0d5c42fddcd6f6d83839b82af791e1abf1dd0252d9850fb47dd33fb`.
No U-Boot environment was saved. The first ordinary boot reached exact v0.10,
the expected root PARTUUID, zero ext4 errors and zero failed units; RTL8188EU,
RK817 charger, Hantro and exFAT all reported matching v0.10 vermagic.

NetworkManager was configured from the exact SSID bytes returned by the live
scan rather than a remembered transcription. Association and DHCP passed, and
the connection automatically returned after both the installer fallback boot
and the final ordinary v0.10 boot. The 263,506,247-byte v0.2 archive was served
read-only by the Mac over the LAN, downloaded to p2 and rehashed as
`53ac09c276fdf69ff1a3764727107f59fbec0859f20329879261d898f27fd620`.
The network credential was not written into tracked bring-up configuration or
the serial evidence.

The installer still intentionally requires exact v0.8. A verified one-shot
loaded the 1,427-byte fallback script (`filesize == 0x593`), then the archive
was extracted to root-owned ext4 staging and exposed at the required `/run`
path with a bind mount. Installation published
`/var/lib/r46h/gaming-mvp-v0.2-installed`; the installed runner and ROM hashes
are respectively `90a71ea1383dbb6b6996e7397d169ea95474d2b082a2ba04b453cf754772ba73`
and `f4e911f38aade8353853127e5e45b91aef1333061bdf865ec1775236e72abb0c`.
The bind mount, extraction tree and downloaded archive were then removed.

An ordinary reboot loaded active v0.10, reconnected Wi-Fi and retained the
receipt/files with zero ext4 errors and failed units. This closes persistent
kernel selection, network delivery and gaming-payload installation. The v0.3
follow-up adds controlled automatic RGUI startup without changing that accepted
v0.2 evidence. EmulationStation, arbitrary ROM copying/compatibility, ADC-stick
integration, v0.12 persistence and a canonical full gaming root image remain
separate work.

### Automatic RGUI v0.3 result (2026-08-16)

Clean commit `bb81c11` produced the 263,512,519-byte v0.3 archive with SHA-256
`644f0359b72b82a1f87c759b55f93327404b8197901674e674496967b5fd4b84`.
The R46H downloaded it over the accepted Wi-Fi link and independently obtained
the same digest. The offline installer found all Debian packages already at the
pinned versions, installed the exact runner, condition and unit, enabled the
unit, then published `/var/lib/r46h/gaming-mvp-v0.3-installed`. Its archive,
root-only extraction tree and `/run` bind mount were removed afterward.

A live `systemctl start` reached RGUI with the service active and RetroArch
running as `ark`. `systemctl stop` removed RetroArch, restored RK817 volume to
`201,201` and mux to `0`, returned to tty1 and left the service cleanly
inactive. A following ordinary reboot loaded exact v0.10 without an autoboot
interrupt and automatically started the service again. Postflight found RGUI
active on tty2, Wi-Fi reconnected, ext4 `errors_count=0`, zero failed units and
no staging residue. Installed hashes matched the committed sources:

- `r46h-game-ui`: `3d34e45ff35a6fa56e4b9d4fae3126dabdc60e1f6397d5419a25899b0f829708`
- frontend condition: `8946a8803c45d264bcf5cc4d29539fd307a82fc6c3d71d51e051648198141a3c`
- systemd unit: `e292769935fc1d5b20185d93b2baed0b5a3603c4ac635e111428c099b838a877`

The fixed configuration deliberately has `config_save_on_exit=false`. Debian
RetroArch currently also derives its history-playlist paths from the read-only
`/etc/r46h` config location, so a controlled stop logs harmless failures to
write `content_*_history.lpl`. This does not affect process cleanup, mixer
restoration or service success, but recent-history persistence remains a small
frontend follow-up and should not be rediscovered as an emulator failure.

### ROM-over-Wi-Fi workflow result (2026-08-16)

The follow-up at clean commit `aacf581` created the system-owned `/roms` root
with `ark`-owned system directories, provisioned `ark`-writable frontend-state
directories, and installed exactly one operator-selected public key for
unprivileged ROM transfer. It did not touch BOOT, EASYROMS or the media layout.
The installed config and root receipt SHA-256 values were respectively
`621fdf049cd05e6aa02c62b5c42ed37a768ce9342af14c4563cfd4466d80d078`
and `d33a1e23c83e2bbcfbb05180aabad4428d99809096f1ca589ddf1be308d2ff27`.

The R46H ED25519 host key was first pinned from CH340 evidence; SSH then used a
dedicated `known_hosts` file with strict checking rather than accepting the
Mac's stale global entry. The original deterministic NES smoke ROM was sent as
a hidden temporary filename, checked on the target against SHA-256
`f4e911f38aade8353853127e5e45b91aef1333061bdf865ec1775236e72abb0c`,
then renamed without overwrite to `/roms/nes/r46h-nes-smoke.nes`. It remained
owned by `ark:ark`, mode `0644`, while RGUI stayed active, ext4 errors stayed at
zero and systemd had no failed unit. Host HTTP/staging and target `/run`
staging were removed after use. This closes the authenticated ROM delivery
workflow for an already validated test ROM; it does not generalize emulator or
commercial-ROM compatibility.

The same run also disproved the attempted recent-history fix: a new service
start/stop still logged `/etc/r46h/content_*_history.lpl`, even though the config
contained absolute user-state paths. Process cleanup passed, the mixer returned
to `201,201`/mux `0`, ext4 errors remained zero and the unit deactivated cleanly,
so this remains a harmless frontend-state limitation rather than an emulator or
ROM-transfer failure. Test `content_history_dir` or a user-owned primary config
separately; do not repeat the ineffective assumption that the individual path
keys alone override Debian RetroArch's config-directory derivation.

After the final postflight the frontend was inactive, no RetroArch process
remained, the mixer was restored to `201,201` with mux `0`, ext4 errors were
zero and systemd had no failed unit. A normal poweroff then remounted p2
read-only, reported all filesystems unmounted, and reached
`systemd-shutdown: Powering off`; five seconds of subsequent CH340 capture were
silent. The 31,821-byte serial evidence has SHA-256
`f1be5ca62a698afeca57a03a8fcb0601f9ddae6fc18e5f63b08963a91765c855`.

### Automatic RGUI ROM launch result (2026-08-17)

One attended cold boot closed the remaining automatic-frontend end-user link.
The serial console opened at 1500000 before power and switched to 115200 at the
exact OP-TEE marker without interrupting autoboot. Exact persistent v0.10
reached multi-user and automatically started `r46h-gaming-frontend.service`.
Preflight confirmed root PARTUUID `c9f931c9-02`, ext4 `errors_count=0`, no
failed unit, active/enabled frontend state, and the expected 24,592-byte ROM at
`/roms/nes/r46h-nes-smoke.nes` with SHA-256
`f4e911f38aade8353853127e5e45b91aef1333061bdf865ec1775236e72abb0c`.

The operator navigated RGUI `Load Content` through `nes` to that exact file and
selected Nestopia. The running process map independently contained
`/usr/lib/aarch64-linux-gnu/libretro/nestopia_libretro.so`. The operator saw the
movable square, confirmed all four D-pad directions moved it, and confirmed A
changed the background from blue to black. This is the accepted automatic
RGUI-to-real-core-and-ROM path; it is not evidence for another ROM or core.

A controlled service stop returned `Result=success` with accepted signal status
143, left no RetroArch process or `/run/r46h-game-ui.*` directory, and restored
RK817 mixer volume `201,201` plus mux `0`. ext4 errors and failed units remained
zero. `sync` plus normal poweroff remounted p2 read-only, unmounted all file
systems and reached `systemd-shutdown: Powering off`; seven following seconds
had no serial bytes. The 65,154-byte evidence is
`mainline/out/r46h-serial-logs/v010-rgui-rom-launch-20260817.bin`, SHA-256
`1bb8fe624676e67b0278472c6e5d97ce8583235616879c39c3489a2d4cee5799`.

The same cold boot independently repeated one
`mmc0: error -84 whilst initialising SD card` at 400 kHz. The driver retried at
300 kHz, then enumerated the same 58.2 GiB card and p1/p2/p3 at SDR104/150 MHz;
a bounded root read passed and no later MMC match, ext4 error or failed unit was
observed. This does not invalidate the gaming result, but it reopens the
cold-MMC gate in the authoritative experiment ledger and must be reviewed
before another cold boot. Do not expand that review into a full-media rewrite
or 125 GB audit without additional storage evidence.
