FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd AS probe-build

ARG DEBIAN_FRONTEND=noninteractive

COPY rootfs-debian13/apt/debian.sources /etc/apt/sources.list.d/debian.sources
COPY rootfs-debian13/apt/99snapshot /etc/apt/apt.conf.d/99snapshot
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libegl-dev \
        libgles-dev \
    && rm -rf /var/lib/apt/lists/*

COPY userspace-probe/r46h-gles2-fbo-probe.c /src/r46h-gles2-fbo-probe.c
RUN cc -std=c11 -O2 -Wall -Wextra -Werror \
      /src/r46h-gles2-fbo-probe.c -o /r46h-gles2-fbo-probe \
      -lEGL -lGLESv2 \
    && strip /r46h-gles2-fbo-probe

FROM debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd

ARG DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Asia/Shanghai

COPY rootfs-debian13/apt/debian.sources /etc/apt/sources.list.d/debian.sources
COPY rootfs-debian13/apt/99snapshot /etc/apt/apt.conf.d/99snapshot
COPY rootfs-debian13/packages.base.txt /tmp/packages.base.txt
COPY rootfs-debian13/packages.hardware.txt /tmp/packages.hardware.txt
COPY rootfs-debian13/packages.graphics.txt /tmp/packages.graphics.txt

RUN set -eux; \
    printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d; \
    chmod 0755 /usr/sbin/policy-rc.d; \
    mkdir -p /usr/share/r46h-build; \
    apt-get update; \
    find /var/lib/apt/lists -maxdepth 1 -type f -name '*InRelease' -print0 \
      | sort -z \
      | xargs -0 sha256sum > /usr/share/r46h-build/APT-INRELEASE-SHA256SUMS; \
    cat /tmp/packages.base.txt /tmp/packages.hardware.txt /tmp/packages.graphics.txt \
      | sed '/^[[:space:]]*$/d' \
      | LC_ALL=C sort -u > /tmp/packages.all.txt; \
    xargs -r apt-get install -y --no-install-recommends < /tmp/packages.all.txt; \
    dpkg-query -W '-f=${binary:Package}\t${Version}\n' \
      | LC_ALL=C sort > /usr/share/r46h-build/PACKAGES.tsv; \
    rm -f /usr/sbin/policy-rc.d; \
    rm -rf /var/lib/apt/lists/* /tmp/packages.*.txt /tmp/packages.all.txt

COPY rootfs-debian13/overlay/ /
COPY rootfs-debian13/overlay/etc/hostname /usr/share/r46h-build/rootfs-config/hostname
COPY rootfs-debian13/overlay/etc/hosts /usr/share/r46h-build/rootfs-config/hosts
COPY rootfs-debian13/build-ext4-in-container.sh /usr/local/libexec/r46h-build-ext4-in-container
COPY --from=probe-build /r46h-gles2-fbo-probe /usr/local/libexec/r46h-gles2-fbo-probe

RUN set -eux; \
    for group in audio input netdev render video; do \
      getent group "$group" >/dev/null || groupadd --system "$group"; \
    done; \
    useradd --uid 1000 --create-home --shell /bin/bash \
      --groups audio,input,netdev,render,sudo,video ark; \
    usermod --password '$6$r46hmvp$s9O/Y19z2LjyY7QEFRyDElh05/Bvk0rHZ914O89HsxZ5UQqH6cQFiEg5DqmnjDpfZxrzbOv95BiJYHYuOjj0f1' ark; \
    passwd --lock root; \
    install -d -m 0755 /boot /roms /var/lib/r46h; \
    install -d -m 0755 \
      /etc/systemd/system/getty.target.wants \
      /etc/systemd/system/multi-user.target.wants \
      /etc/systemd/system/network-pre.target.wants; \
    ln -sfn /lib/systemd/system/serial-getty@.service \
      /etc/systemd/system/getty.target.wants/serial-getty@ttyS2.service; \
    ln -sfn /usr/share/zoneinfo/Asia/Shanghai /etc/localtime; \
    printf 'Asia/Shanghai\n' > /etc/timezone; \
    ln -sfn /lib/systemd/system/ssh.service \
      /etc/systemd/system/multi-user.target.wants/ssh.service; \
    ln -sfn /lib/systemd/system/NetworkManager.service \
      /etc/systemd/system/multi-user.target.wants/NetworkManager.service; \
    ln -sfn /etc/systemd/system/r46h-firstboot.service \
      /etc/systemd/system/multi-user.target.wants/r46h-firstboot.service; \
    ln -sfn /etc/systemd/system/r46h-wifi-mac.service \
      /etc/systemd/system/network-pre.target.wants/r46h-wifi-mac.service; \
    ln -sf /lib/systemd/system/multi-user.target /etc/systemd/system/default.target; \
    ln -sf /dev/null /etc/systemd/system/NetworkManager-wait-online.service; \
    ln -sf /dev/null /etc/systemd/system/systemd-firstboot.service; \
    ln -sf /dev/null /etc/systemd/system/alsa-restore.service; \
    ln -sf /dev/null /etc/systemd/system/alsa-state.service; \
    install -d -o root -g root -m 0755 /run/sshd; \
    /usr/sbin/sshd -T | LC_ALL=C sort > /usr/share/r46h-build/SSHD-EFFECTIVE.txt; \
    grep -Fqx 'permitrootlogin no' /usr/share/r46h-build/SSHD-EFFECTIVE.txt; \
    grep -Fqx 'passwordauthentication no' /usr/share/r46h-build/SSHD-EFFECTIVE.txt; \
    grep -Fqx 'kbdinteractiveauthentication no' /usr/share/r46h-build/SSHD-EFFECTIVE.txt; \
    grep -Fqx 'x11forwarding no' /usr/share/r46h-build/SSHD-EFFECTIVE.txt; \
    grep -Fqx 'allowusers ark' /usr/share/r46h-build/SSHD-EFFECTIVE.txt; \
    chmod 0755 \
      /usr/libexec/r46h-firstboot \
      /usr/libexec/r46h-wifi-mac \
      /usr/local/libexec/r46h-build-ext4-in-container \
      /usr/local/libexec/r46h-gles2-fbo-probe \
      /usr/local/sbin/r46h-rootfs-smoke; \
    chmod 0440 /etc/sudoers.d/90-r46h-ark; \
    rm -f /etc/ssh/ssh_host_* /var/lib/dbus/machine-id; \
    : > /etc/machine-id; \
    ln -s /etc/machine-id /var/lib/dbus/machine-id; \
    test -f /lib/firmware/rtlwifi/rtl8188eufw.bin; \
    test -f /usr/lib/aarch64-linux-gnu/dri/panfrost_dri.so; \
    test -s /usr/share/r46h-build/rootfs-config/hostname; \
    test -s /usr/share/r46h-build/rootfs-config/hosts; \
    ! find / -xdev -iname 'libMali*' -print -quit | grep -q .

CMD ["/bin/bash"]
