# R46H Debian 13 gaming p2 v0.15

Status: **HOST + P2 MEDIA + DEVICE AUTOMATION PASS / ATTENDED OPEN / DREAMCAST FAIL**

This is the minimal Game Gear successor to exact p2 v0.14. It adds the pinned
Debian 13 arm64 Genesis Plus GX core, one ES-DE system, 105 audited
original-card entries and 105 existing cover links. No firmware, ROM or save
is packaged. BOOT, p1 and p3 stay outside the image and write plan.

```sh
PYTHONDONTWRITEBYTECODE=1 mainline/gaming-genesisplusgx/generate-filtered-gamelist.py \
  --rom-root mainline/out/.cache/r46h-original-card-import-20260826/easyroms \
  --base-media mainline/out/r46h-gaming-flycast-content-v0.1/legacy-media-links.tsv \
  --output-root mainline/out/r46h-gaming-genesisplusgx-content-v0.1

PYTHONDONTWRITEBYTECODE=1 mainline/scripts/build-debian13-gaming-rootfs-v15.py validate-inputs
PYTHONDONTWRITEBYTECODE=1 mainline/scripts/build-debian13-gaming-rootfs-v15.py build
PYTHONDONTWRITEBYTECODE=1 mainline/scripts/build-debian13-gaming-rootfs-v15.py validate

PYTHONDONTWRITEBYTECODE=1 mainline/scripts/generate-debian13-write-plan.py \
  --device /dev/diskN \
  --profile-id hl-r46h-v22-g92-62534975488-v1 \
  --artifact-id debian13-p2-gaming-v0.15 \
  --target-sha256-before <independent-full-p2-sha256>
```

The offline composer writes no block device. It checks exact package/core and
license identities, all 14 systems, the 105-entry Game Gear gamelist, 6,220
media links, the retained emulator stack and direct readback.

Two full builds from source commit
`a40e07d5eaec7bd164752e58f6f940f375cd5a97` were byte-identical, followed by
a separate post-publish validation:

- image size: `10,716,877,312` bytes
- image SHA-256: `a69c2dafeae76f37a6e582bfdf4887d5714b82a4cf5b3dc7a84e29f36be6e893`
- `BUILD-INFO` SHA-256: `f6533599f9c94997438170ac38e5a49eec9b13aa216cb20cde797cbf952968d0`
- consolidated receipt SHA-256: `7a3d4fa07e4a34f9313e1fd4a84c66389cbb7a9cfc740659f241461e4a01524d`

## P2 media pass

On 2026-09-04, audit session
`session-20260904T142652Z-81185-689e7e8e-1d22-4288-9db6-779e88093d59`
fixed that insertion as `/dev/disk12`, retained the complete old p2 clone and
reproduced its SHA-256 twice as
`319ec8aef35a6624c967a2b592e89976fbddd8e362c8e835b96f47806fc5c32a`.

Pinned plan SHA-256
`ffa73ebf1e4b7857e6fbea3c13050fd26004007ee10bd587b5bc53eea79b93c5`
opened only p2. Deploy session
`session-20260904T153639Z-82818-6a3c72c4-c52b-4749-9837-6c079aefc5d7`
wrote the published image; its complete transaction readback and a separate
raw p2 hash both equal the source SHA-256. `WRITE_COMPLETE` and
`safe_to_boot=yes` passed. BOOT matched before/after at
`12ea8821cad224fd5da45ea2bfd30f921a8dbc15d2df41700a57e233a308cd0e`,
the fixed prefix remained exact, p3 stayed unmounted and outside the plan, and
macOS confirmed eject. The retained write receipt SHA-256 is
`929d3b628824895875cfcf9cee9cc5db6988bbabf0d2d5825e3c3ce556d77424`.

## Device batch

On 2026-09-05 the current card cold-booted the exact v0.15 kernel and p2 UUID.
The installed read-only storage audit passed SDR104 at 150 MHz and the complete
rootfs smoke passed. ES-DE auto-started with `/roms` read-only and all product
services at zero restarts.

Unattended samples then passed these machine-visible boundaries:

- Game Gear `001.zip` ran Genesis Plus GX for 748 seconds with a valid captured
  frame and PCM running.
- PSP `我的世界PSP.PBP` ran PPSSPP for 639 seconds with a valid menu frame and PCM
  running; its process changes `comm` to `Main`.
- CPS2 `mpang.zip` ran FBNeo for 148 seconds with a valid demo frame and PCM
  running.

[Flycast](../gaming-flycast/README.md) failed after entering Dreamcast gameplay.
Temporary graphics settings and diagnostic binaries were removed, shipped
configuration hashes were restored, and a warm reboot again passed SDR104,
rootfs/GPU health, ES-DE capture/removal and zero restarts/errors. `sync` plus
controlled poweroff reached `Powering off`. The retained serial log is
`mainline/out/.cache/r46h-v15-physical/serial/cold-boot-20260905.log`, 3,412,816
bytes, SHA-256 `a74508a956f98b2d113a65074434ed595b6b5283e7d230f98fa90ad448e63523`.

No operator was present, so LCD motion, audible output, physical controls and
save persistence remain open. V0.15 has no saved Wi-Fi profile or IPv4, so its
strict-SSH host key was not paired. P2 v0.16 later passed its packaged
[remote input](../gaming-remote-input/README.md) and
[screen guard](../gaming-remote-screen/README.md) device gates, but ES-DE merged
bundled Dreamcast. P2 v0.17 owns the proven exclusive-system fix.
