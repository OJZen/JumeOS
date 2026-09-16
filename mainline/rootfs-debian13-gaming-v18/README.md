# R46H Debian 13 gaming p2 v0.18

Status: **HOST BUILDER READY / MEDIA + DEVICE OPEN**

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

Media write/readback and physical acceptance are separate. After a guarded p2
write, verify cold identity, a newly changed ark password, scan/profile
create-delete/reconnect, denial of unrelated polkit actions, warm-reboot
persistence, product health, sync and controlled poweroff.
