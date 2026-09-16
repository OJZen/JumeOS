# R46H Debian 13 gaming p2 v0.18

Status: **HOST PASS / MEDIA + DEVICE OPEN**

This is the exact v0.17 successor for local Wi-Fi control. It installs Debian
13's exact `polkitd` dependency set and the target-tested ark-only three-action
rule. ES-DE, games, services and the v0.15 product kernel remain unchanged.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v18.py validate-inputs
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v18.py build
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v18.py validate
```

The offline builder uses the published v0.17 image and hash-pinned local `.deb`
files. A privileged container mounts only private image/scratch files; it never
opens a host block device. The final ext4 is rebuilt with `mke2fs -d`, normalized
and composed twice byte-for-byte before publication. BOOT, p1, p3 and the R46H
remain outside the host build.

Source commit `4cdf340a7c6ecf1ba4bd1c501341a0e35c6f2933` produced two
byte-identical images and passed a separate post-publish validation:

- image SHA-256: `461d47535870568c854b1edf7016629a6fa66a60da81915c14449ac8700c4cae`
- `BUILD-INFO` SHA-256: `1ee96f46377d3fb579adae226b5eba8f86cde2bc3efe4b5920b256e20391fadd`
- consolidated receipt SHA-256: `839848705ad9e3a1c097fe7d4e9442df7ea5338f3072a0af9aa0dfd811a638dd`

Media write/readback and physical acceptance are separate. After a guarded p2
write, verify cold identity, a newly changed ark password, scan/profile
create-delete/reconnect, denial of unrelated polkit actions, warm-reboot
persistence, product health, sync and controlled poweroff.
