# R46H vendor-kernel headphone GPIO control

Status: **V0.1 PHYSICAL INFRASTRUCTURE FAIL / V0.2 CONCLUSIVE PHYSICAL
NO-TRANSITION / GPIO CONTROL CLOSED / PHYSICAL OUTPUT LATER PASSED SEPARATELY /
AUTOMATIC DAPM MUTING UNTESTED**

The exact v0.10 localizer saw neither an RK817 evdev transition nor a raw
GPIO2_C6 transition during one complete headset insertion/removal cycle. The
completed follow-up changed the hypothesis instead of repeating that probe: it
booted the retained factory `4.4.189` kernel and factory DTB once, then sampled
the same already-requested active-low GPIO2_C6 line from a minimal initramfs.

This is a control experiment, not a fix. It does not request or drive a GPIO,
change pinctrl, start the factory root filesystem, start normal userspace,
touch a mixer or play audio. A result can narrow the next investigation, but
cannot by itself prove a damaged socket, a good headset, or one specific
mainline driver defect.

A later changed v0.4 route gate did not rerun this control. It independently
passed physical headphone output and effective mechanical speaker cut-off on
exact mainline v0.10 while leaving automatic jack reporting/DAPM muting open;
see [`AUDIO-ROUTE-PROBE.md`](AUDIO-ROUTE-PROBE.md). That later result does not
alter the conclusive v0.2 no-transition boundary below.

The exact v0.1 artifact ran once on 2026-08-21. It loaded the retained factory
Image/DTB and minimal ramdisk successfully, reached exact kernel `4.4.189` and
the PID-1 ready marker, then stopped before the observation marker with:

```text
result=fail reason=initial-gpio-state-unreadable localization=none
initial_raw=-1 insertions=0 removals=0 final_raw=-1 samples=0
R46H_AUDIO_JACK_VENDOR_CONTROL_COMMAND status=1
R46H_AUDIO_JACK_VENDOR_CONTROL_POWEROFF status=1
```

No headset action occurred. The exact failure does not expose whether opening,
reading or parsing debugfs failed, and v0.1's parser made the vendor-only `IRQ`
suffix a mandatory identity check without physical runtime proof that this BSP
sets gpiolib's `FLAG_USED_AS_IRQ`. Record this as an infrastructure failure and
do not promote it to either factory GPIO outcome. A changed follow-up must add
read-stage observability and may accept an otherwise exact requested input line
with or without that suffix; do not repeat v0.1 unchanged.

## Changed v0.2 source boundary

Current
[`r46h-audio-jack-vendor-control.c`](r46h-audio-jack-vendor-control.c) is v0.2,
from clean commit `c360b632b77d0ed785dc6895a5bbf399447bca49`, SHA-256
`8684cd88355b1012b8c993fb55b47d6fc0ec5c126389d24fcde1e4878ad311d2`.
It keeps the exact factory release/model, `/init` identity, unique consumer,
`gpio-86`, input direction, high/low grammar, 30-second bound, read-only mounts
and automatic poweroff. The only acceptance change is that the exact v4.4 line
may end either with `IRQ` or whitespace; v0.2 reports `irq=present` or
`irq=absent` and requires that identity to remain stable throughout the run.
An extra suffix token, output direction, wrong number, missing/duplicate
consumer or invalid state still fails closed.

Before any observation marker, a successful first read now emits the parsed
line identity. An open, metadata, read, close or parse failure emits a separate
`GPIO_READ` marker with sample `phase`, failure `stage` and numeric `errno`
before the unchanged
terminal reason:

```text
R46H_AUDIO_JACK_VENDOR_CONTROL_GPIO_LINE gpio=gpio-86 consumer=Headphone_detection direction=input raw=high irq=present|absent
R46H_AUDIO_JACK_VENDOR_CONTROL_GPIO_READ phase=initial stage=open|metadata|read|close|parse result=fail errno=N
```

The pinned ARM64 Linux image compiled v0.2 statically with
`-Wall -Wextra -Werror`; its self-test accepted exact lines both with and
without `IRQ`, rejected wrong/output/extra-token/duplicate fixtures and passed
the bounded classification path. Full GCC analyzer output contained only its
pre-existing PID-1 console `dup2(0/1/2)` lifetime warnings; the remaining
analysis passed with `-Wno-analyzer-fd-leak`, matching the design in which a
successful poweroff does not return and the three descriptors are closed only
on the failure-return path. The deterministic artifact below was then built
from that clean commit and used for the single physical control recorded next.

## 2026-08-22 v0.2 physical result

The changed control ran exactly once. Exact persistent v0.10 first rehashed the
current p1 factory Image and DTB read-only, staged only the reviewed 353,017-byte
`uInitrd`, verified its source and root-owned copies, retained zero ext4 errors
and failed units, and powered off normally. The one-shot then loaded the three
size-pinned factory inputs, passed `iminfo`, booted exact Linux `4.4.189` and
reached the observation marker with persistent storage unmounted and normal
userspace absent. The factory debug line was the exact input identity with its
optional runtime IRQ column absent:

```text
R46H_AUDIO_JACK_VENDOR_CONTROL_GPIO_LINE gpio=gpio-86 consumer=Headphone_detection direction=input raw=high irq=absent
R46H_AUDIO_JACK_VENDOR_CONTROL_OBSERVATION phase=start gpio=gpio-86 seconds=30 sample_ms=20 action=insert-once-then-remove-once
```

The operator fully inserted the known headset, held it for about two seconds,
then removed it once and left it removed. All 1,463 valid samples remained raw
high, and the exact terminal result was:

```text
R46H_AUDIO_JACK_VENDOR_CONTROL id=r46h-audio-jack-vendor-control-v0.2 kernel=4.4.189 result=fail reason=vendor-gpio-transitions-missing localization=shared-electrical-socket-or-common-pin-state initial_raw=1 insertions=0 removals=0 final_raw=1 samples=1463
R46H_AUDIO_JACK_VENDOR_CONTROL_COMMAND status=1
R46H_AUDIO_JACK_VENDOR_CONTROL_POWEROFF status=1
```

PID 1 then reached `reboot: Power down`. This is the contract's conclusive
no-transition outcome: mainline and factory both left the shared active-low
line high during attended insertion/removal. Investigate the shared
electrical/socket/plug or common pin-state boundary next. This result does not
prove a damaged socket, a defective headset or any one root cause, and it does
not test headphone output or automatic speaker muting. Do not repeat this
unchanged v0.2 control.

The following ordinary exact-v0.10 boot independently rehashed and removed both
staged copies and their empty directories. P1 remained unmounted, the accepted
History/config identities remained exact, ext4 errors and failed units stayed
zero, the gaming frontend remained active, and serial confirmed controlled
poweroff. The staging v0.10 cold boot reproduced the known recoverable 400/300
kHz initialization `-84`; the cleanup v0.10 cold boot omitted it and reached
SDR104 directly. Neither had a later storage fault.

| Serial evidence | Bytes | SHA-256 |
| --- | ---: | --- |
| exact v0.10 p1 check, staging and controlled poweroff: `mainline/out/r46h-serial-logs/vendor-control-v02-staging-v010-20260822.bin` | 59,848 | `33722e159593409beb1774a6dc2aae0614a34eab96581cd3c49e3be9b79ad0ab` |
| exact factory-4.4 v0.2 control and automatic poweroff: `mainline/out/r46h-serial-logs/vendor-control-v02-factory-20260822.bin` | 55,320 | `445a5a3d68315a13cb59c4a6fed456b44fefa9eeeca6d7e78260181993076c22` |
| exact v0.10 cleanup, health checks and controlled poweroff: `mainline/out/r46h-serial-logs/vendor-control-v02-cleanup-v010-20260822.bin` | 59,016 | `b26ac35b8eb3ea2ecfde4e644763e3ea154b0bf000734b40638bab77a8d96427` |

## Why the factory control was selected

The retained factory DTB and the active mainline DTS both select GPIO2_C6 as
an active-low headphone-detect input:

```text
factory: simple-audio-card,hp-det-gpio = <gpio2 22 GPIO_ACTIVE_LOW>
mainline: simple-audio-card,hp-det-gpio = <&gpio2 RK_PC6 GPIO_ACTIVE_LOW>
```

The factory DTB also sets `simple-audio-card,codec-hp-det`, while its alternate
PDM use of GPIO2_C6 is disabled. The retained factory Image identifies itself
as Linux `4.4.189` and contains the RK817 codec, simple-card headphone-detect
and `Headphone detection` consumer strings. Its GPIO debug format strings match
the [upstream-v4.4 optional-IRQ-column
layout](https://github.com/torvalds/linux/blob/v4.4/drivers/gpio/gpiolib.c)
and contain no `ACTIVE LOW` literal. On mainline, debugfs showed the same
consumer on `gpio-86`, input-high, IRQ active-low, with the pin configured as
GPIO2_C6 and pull-down. V0.1 incorrectly promoted the vendor runtime `IRQ`
suffix from a useful observation into a mandatory identity requirement. V0.2
instead obtains polarity from the exact hashed DTB and treats the suffix as
reported runtime state while retaining every number/name/direction/value
guard. These checks rule out a speculative pin-number or polarity flip as the
next step; they do not rule out a software configuration, electrical, trace,
socket or plug-fit problem.

The physical comparison has two deliberately narrow outcomes:

| Factory result | Bounded interpretation |
| --- | --- |
| `vendor-gpio-cycle-observed` | The same hardware can toggle under the factory stack; investigate a mainline-specific pinctrl/GPIO/ASoC path. This is a suspect boundary, not a final cause. |
| `vendor-gpio-transitions-missing` | Both stacks remained high; investigate the shared electrical/socket/plug or common pin-state boundary. This still does not prove hardware damage. |

Do not repeat the unchanged v0.10 localizer or completed v0.2 control, change
the DTS, or run headphone playback merely because this comparison is complete.
This control does not authorize headphone playback.

## Frozen v0.2 source and deterministic initramfs

The current v0.2 source is frozen at commit
`c360b632b77d0ed785dc6895a5bbf399447bca49`, SHA-256
`8684cd88355b1012b8c993fb55b47d6fc0ec5c126389d24fcde1e4878ad311d2`.
It is a static initramfs PID 1 pinned to:

- exact kernel release `4.4.189` and model `GameConsole R46H`;
- executable identity `/init`, root ownership, mode `0700`, one regular link;
- exactly one debugfs line containing `gpio-86`, `Headphone detection`, input
  direction and raw high/low state; the factory-v4.4 `IRQ` column is recorded
  as present or absent, while the active-low identity remains pinned by the
  exact factory DTB;
- one 30-second maximum window sampled every 20 ms, starting and finishing
  raw-high with the headset removed.

PID 1 mounts only devtmpfs plus read-only procfs, sysfs and debugfs. Before
producing a user marker it opens `/dev/console` without following links,
requires the exact character device major/minor `5:1`, binds all three
standard descriptors and requires them to be TTYs. It then runs the bounded
sampler and calls poweroff. It never mounts a block device or persistent
filesystem. Its source contains no GPIO-request API, evdev grab, audio
operation, subprocess or normal userspace startup.

The following recipe is valid only with that exact clean commit. Retain build
outputs below the external repository cache. The builder tag resolved to exact
local image ID
`sha256:6b4a05209b13e72ae2ae02056f14fe75d79b4ba8b8b0f6d403559c0e6921158c`;
verify it before running the tag. Require a previously absent work directory:

```bash
test "$(git rev-parse HEAD)" = c360b632b77d0ed785dc6895a5bbf399447bca49
test -z "$(git status --porcelain)"
test "$(docker image inspect --format '{{.Id}}' \
  arkos4clone/r46h-kernel-builder:trixie-arm64)" = \
  sha256:6b4a05209b13e72ae2ae02056f14fe75d79b4ba8b8b0f6d403559c0e6921158c
test ! -e mainline/out/.cache/r46h-audio-jack-vendor-control-v0.2
mkdir mainline/out/.cache/r46h-audio-jack-vendor-control-v0.2

docker run --rm --platform linux/arm64 --network none \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/repo:ro" \
  -v "$PWD/mainline/out/.cache/r46h-audio-jack-vendor-control-v0.2:/work" \
  -w /work arkos4clone/r46h-kernel-builder:trixie-arm64 \
  /usr/bin/cc -std=c11 -O2 -Wall -Wextra -Werror -static \
  -o /work/r46h-audio-jack-vendor-control \
  /repo/mainline/bringup-tests/r46h-audio-jack-vendor-control.c

docker run --rm --platform linux/arm64 --network none \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/mainline/out/.cache/r46h-audio-jack-vendor-control-v0.2:/work" \
  -w /work arkos4clone/r46h-kernel-builder:trixie-arm64 \
  /bin/bash -euo pipefail -c '
    stage=$(mktemp -d /tmp/r46h-audio-jack-vendor-control-v0.2.XXXXXX)
    chmod 0755 "$stage"
    install -d -m 0755 "$stage/dev"
    install -d -m 0555 "$stage/proc" "$stage/sys"
    install -m 0700 /work/r46h-audio-jack-vendor-control "$stage/init"
    find "$stage" -exec touch -h -d @0 {} +
    cd "$stage"
    find . -print0 | sort -z |
      cpio --null --create --format=newc --owner=0:0 --reproducible \
      > /work/initramfs.cpio
  '

printf '%s  %s\n' \
  '4fef8dd687478d1a8dcf4e2db25defd2daf76f7e0bb3478f023b738f9501f48c' \
  /opt/homebrew/bin/lz4 | /usr/bin/shasum -a 256 -c -
/opt/homebrew/bin/lz4 -q -f -l -12 -T1 \
  mainline/out/.cache/r46h-audio-jack-vendor-control-v0.2/initramfs.cpio \
  mainline/out/.cache/r46h-audio-jack-vendor-control-v0.2/initramfs.cpio.lz4

docker run --rm --platform linux/arm64 --network none \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/mainline/out/.cache/r46h-audio-jack-vendor-control-v0.2:/work" \
  -w /work arkos4clone/r46h-kernel-builder:trixie-arm64 \
  /bin/bash -euo pipefail -c '
    SOURCE_DATE_EPOCH=0 mkimage -A arm -O linux -T ramdisk -C gzip \
      -a 0 -e 0 -n "R46H vendor jack control v0.2" \
      -d initramfs.cpio.lz4 uInitrd
  '
```

The exact host LZ4 tool is v1.10.0. Legacy mode is required because the
retained, physically booted factory ramdisk uses the same `02 21 4c 18` frame
and the factory Image is proven to support `CONFIG_RD_LZ4`; gzip decompression
was not promoted from assumption to evidence. The legacy U-Boot header keeps
the factory-compatible `gzip` type tag, just like the retained factory
`uInitrd`, but `booti` receives the header-stripped legacy-LZ4 payload and the
kernel detects its actual compression format.

The tiny cpio staging tree is deliberately created inside the disposable
`--rm` container: Docker Desktop broadens a host-bind-mounted mode `0700` file
to `0755` in the Linux view. Container-local staging preserves the reviewed
root-owned mode-`0700` `/init`; only the final files remain in the external
cache.

The reviewed v0.2 outputs are:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| static AArch64 `/init` | 708,488 | `2be2a1909319c8276db9876f13b5fef47e628ae333ec5962d1f304a0ad337057` |
| deterministic newc cpio | 709,632 | `4259f91bcf6ab2d4db3d1449b9a94a372f6d2422443b3c08406d5a8d90022489` |
| deterministic legacy-LZ4 cpio | 352,953 | `9e4da0bcded50ed29313b9630af9c044da234e332b20d576aa0ebe67befc360e` |
| legacy ARM Linux RAMDisk `uInitrd` | 353,017 | `b6403a97c0e465bd2f977d5ac557c0dc28ab6cb27b01424b843a7605b0bb67ff` |

The cpio contains exactly `.`, `/dev`, mode-`0700` root-owned `/init`, `/proc`
and `/sys`; every entry has epoch mtime. Two independent cpio, legacy-LZ4 and
U-Boot packaging passes were byte-identical. `dumpimage -l` reports a valid
ARM Linux RAMDisk named `R46H vendor jack control v0.2`, epoch timestamp and a
352,953-byte data payload. Extracting its payload reproduces the reviewed
legacy-LZ4 file, `lz4 -t` passes, decompression reproduces the reviewed cpio,
and the static binary self-test passes in the pinned ARM64 container. These
are host-artifact results only. The build used GCC 14.2.0, GNU cpio 2.15,
mkimage 2025.01 and host LZ4 1.10.0.

For historical identification only, the physically attempted v0.1 source is
frozen at commit `a093de179ee2565df0fa091dc40553a565699e7c`, SHA-256
`629d59e7e79c90681d380e1a727ddbaa5bad4737d819e6985b8b6153f971cd3a`.
Its static binary, cpio, legacy-LZ4 payload and `uInitrd` were respectively
708,456, 709,632, 351,956 and 352,020 bytes, with SHA-256
`6b0c654b68c154e44ee372388a99a88efadbe82fbb403c6f038e7432183fbfbe`,
`5c7b7c6202d0652f6e222b0b5f1c0edd87a687c4ff84a3a831b97cd7ad638562`,
`04d40cb81cf34048cb4f3be91e80ccbc72ba6d84edc4704a33be89d8eee81e34`
and `32f4f0ec8c5924cf31b3743a0f316950050caa38c3c4e41763a4eecd73650f1e`.
That artifact produced only the infrastructure failure recorded above; do not
rebuild, restage or rerun it.

## Frozen factory boot inputs

Use the factory files already retained on p1; do not rewrite BOOT and do not
replace them with files copied from an old log or another card:

| p1 file | Bytes | SHA-256 |
| --- | ---: | --- |
| `Image` | 13,096,968 | `eda795942083d198d7223dcf3f65e19c05c4c7bfc754935e4f84d3a0cc15bbfd` |
| `rk3326-r46h-linux.dtb` | 93,698 | `ff42fbf07d9455b483f2e21eef074a7b2bcb13eb3ca2cba7c40b1193d6c79af8` |

The retained 117,440,512-byte p1 image has SHA-256
`88c6d614984791b891e63068ea687dabe28eb80c905a2aa9c6dd34409b24f86d`,
but that host image was not promoted to current-media proof. Before the physical
control, exact v0.10 mounted current p1 read-only, rehashed the two files above
and unmounted it. P1 PARTUUID was `c9f931c9-01`; p2 remained `c9f931c9-02`.

## Frozen inactive p2 staging procedure (completed; do not rerun)

The 2026-08-22 attended batch used the following procedure once. It is retained
only to identify the accepted evidence; do not restage it. The batch transferred
only the reviewed v0.2 `uInitrd` over the authenticated Wi-Fi path, rehashed it
as unprivileged `ark`, then published one inactive root-owned file while exact
persistent v0.10 was healthy:

```bash
printf '%s  %s\n' \
  'b6403a97c0e465bd2f977d5ac557c0dc28ab6cb27b01424b843a7605b0bb67ff' \
  /home/ark/.cache/r46h-audio-jack-vendor-control-v0.2/uInitrd | sha256sum -c -
test -f /home/ark/.cache/r46h-audio-jack-vendor-control-v0.2/uInitrd
test ! -L /home/ark/.cache/r46h-audio-jack-vendor-control-v0.2/uInitrd
chmod 0600 /home/ark/.cache/r46h-audio-jack-vendor-control-v0.2/uInitrd
test "$(stat -c '%u:%g:%a:%h' \
  /home/ark/.cache/r46h-audio-jack-vendor-control-v0.2/uInitrd)" = \
  "$(id -u):$(id -g):600:1"
sudo test ! -e /var/lib/r46h/audio-jack-vendor-control-v0.2
sudo install -d -o root -g root -m 0700 \
  /var/lib/r46h/audio-jack-vendor-control-v0.2
sudo install -o root -g root -m 0600 \
  /home/ark/.cache/r46h-audio-jack-vendor-control-v0.2/uInitrd \
  /var/lib/r46h/audio-jack-vendor-control-v0.2/uInitrd
printf '%s  %s\n' \
  'b6403a97c0e465bd2f977d5ac557c0dc28ab6cb27b01424b843a7605b0bb67ff' \
  /var/lib/r46h/audio-jack-vendor-control-v0.2/uInitrd |
  sudo sha256sum -c -
```

Require the directory to be root-owned mode `0700`, the file to be root-owned
mode `0600` with one link, and the gaming frontend to remain unchanged. Run
`sync` and power off normally. This p2 file is only a U-Boot-readable ramdisk;
it is never started under v0.10 and does not alter p1 or the persistent U-Boot
environment.

## Frozen factory-kernel one-shot (completed; do not rerun)

The batch opened cold serial at 1,500,000 before applying power, switched to
115,200 only after the visible `I/TC: OP-TEE version` marker, interrupted
autoboot once, and entered the following reviewed commands individually. It
never used `saveenv` or sourced this Markdown block:

```text
mmc dev 1
setenv loadaddr 0x02000000
setenv initrd_loadaddr 0x01100000
setenv dtb_loadaddr 0x01f00000
setenv bootargs "rdinit=/init console=/dev/ttyFIQ0 consoleblank=0 max_cpufreq=1296 boot_cpufreq=1248 max_gpufreq=520 max_ddrfreq=666"
if fatload mmc 1:1 ${loadaddr} Image; then
  if itest ${filesize} -eq 0xc7d808; then
    if fatload mmc 1:1 ${dtb_loadaddr} rk3326-r46h-linux.dtb; then
      if itest ${filesize} -eq 0x16e02; then
        if ext4load mmc 1:2 ${initrd_loadaddr} /var/lib/r46h/audio-jack-vendor-control-v0.2/uInitrd; then
          if itest ${filesize} -eq 0x562f9; then
            if iminfo ${initrd_loadaddr}; then
              booti ${loadaddr} 0x01100040:0x000562b9 ${dtb_loadaddr}
            else
              echo "R46H vendor jack control: ramdisk checksum failed"
            fi
          else
            echo "R46H vendor jack control: ramdisk size mismatch"
          fi
        else
          echo "R46H vendor jack control: ramdisk load failed"
        fi
      else
        echo "R46H vendor jack control: DTB size mismatch"
      fi
    else
      echo "R46H vendor jack control: DTB load failed"
    fi
  else
    echo "R46H vendor jack control: Image size mismatch"
  fi
else
  echo "R46H vendor jack control: Image load failed"
fi
```

Every failed load, size or `iminfo` branch stops at U-Boot; use no fallback
command except an ordinary later v0.10 boot. The raw ramdisk payload begins at
`0x01100040` and is exactly `0x000562b9` bytes, matching the validated legacy
header and legacy-LZ4 payload. P1 and p2 are read only by U-Boot. Linux
receives only the factory Image, factory DTB and the minimal in-memory root;
no block filesystem is mounted by PID 1.

Start with the headset removed. A readable line must first identify the exact
input and its observed IRQ state, then open the attended action window:

```text
R46H_AUDIO_JACK_VENDOR_CONTROL_INIT phase=ready persistent_storage_mounted=no normal_userspace_started=no
R46H_AUDIO_JACK_VENDOR_CONTROL_GPIO_LINE gpio=gpio-86 consumer=Headphone_detection direction=input raw=high irq=present|absent
R46H_AUDIO_JACK_VENDOR_CONTROL_OBSERVATION phase=start gpio=gpio-86 seconds=30 sample_ms=20 action=insert-once-then-remove-once
```

If `GPIO_READ phase=initial stage=... result=fail errno=...` appears instead,
do not insert the headset. Preserve the terminal failure and automatic
poweroff as infrastructure evidence. A later sample/final read failure or IRQ
identity change likewise invalidates the GPIO outcome rather than proving a
transition result.

Fully insert the known headset once, hold it for about two seconds, then remove
it once and leave it removed. The window exits early after a complete raw
low/high cycle or automatically at 30 seconds. Accept only a terminal result
with exact kernel `4.4.189`, initial/final raw-high and the matching command
status: an observed cycle is `result=pass` with command/poweroff status `0`;
the conclusive no-transition result is `result=fail` with reason
`vendor-gpio-transitions-missing` and command/poweroff status `1`. PID 1 then
unmounts its four pseudo filesystems, calls `sync` with no persistent mount and
powers off. Retain serial through the final power-down marker.

Do not repeat this unchanged control after either conclusive result. If setup,
identity, framing, final-removal or poweroff fails, record an infrastructure
failure rather than promoting it to a GPIO result.

## Frozen exact cleanup (completed; do not rerun)

After the factory one-shot powered off, an ordinary healthy exact-v0.10 boot
used the following procedure to independently rehash and remove only the staged
files and their empty directories:

```bash
printf '%s  %s\n' \
  'b6403a97c0e465bd2f977d5ac557c0dc28ab6cb27b01424b843a7605b0bb67ff' \
  /var/lib/r46h/audio-jack-vendor-control-v0.2/uInitrd |
  sudo sha256sum -c -
test "$(sudo stat -c '%u:%g:%a:%h' \
  /var/lib/r46h/audio-jack-vendor-control-v0.2/uInitrd)" = 0:0:600:1
sudo rm -f /var/lib/r46h/audio-jack-vendor-control-v0.2/uInitrd
sudo rmdir /var/lib/r46h/audio-jack-vendor-control-v0.2
printf '%s  %s\n' \
  'b6403a97c0e465bd2f977d5ac557c0dc28ab6cb27b01424b843a7605b0bb67ff' \
  /home/ark/.cache/r46h-audio-jack-vendor-control-v0.2/uInitrd |
  sha256sum -c -
test "$(stat -c '%u:%g:%a:%h' \
  /home/ark/.cache/r46h-audio-jack-vendor-control-v0.2/uInitrd)" = \
  "$(id -u):$(id -g):600:1"
rm -f /home/ark/.cache/r46h-audio-jack-vendor-control-v0.2/uInitrd
rmdir /home/ark/.cache/r46h-audio-jack-vendor-control-v0.2
```

The completed cleanup preserved unrelated cache entries. A future runbook may
link this frozen contract but must not copy or weaken its identity, stop or
cleanup checks, and must not rerun the unchanged control.
