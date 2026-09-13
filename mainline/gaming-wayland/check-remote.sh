#!/bin/bash
# Real SSH inside a network-disabled SDK container; no host key/service is reused.
set -Eeuo pipefail
[[ -f /.dockerenv && -f /candidate.tar.gz && -d /ssh-debs && ( $# == 0 || $# == 1 && $1 == --working-source ) ]] || exit 2
mkdir -p /out/remote /project/mainline/out/.cache
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
chmod 755 /usr/sbin/policy-rc.d
dpkg -i /debs/*.deb /ssh-debs/*.deb > /out/remote/setup.log 2>&1
dpkg-query -W openssh-server openssh-client iproute2 > /out/remote/versions.txt
if [[ $# == 1 ]]; then
  cmake -S /src -B /out/linux-build -DCMAKE_BUILD_TYPE=Release
  cmake --build /out/linux-build -j 3
fi
id ark >/dev/null 2>&1 || useradd -m -u 1000 -s /bin/sh ark
usermod -p '*' ark
mkdir -p /run/sshd /run/r46h-wayland-probe
chmod 755 /run/sshd /run/r46h-wayland-probe
tar -xzf /candidate.tar.gz -C /run/r46h-wayland-probe
install -m 755 /src/remote-session.sh /src/shell-client.sh /run/r46h-wayland-probe/
install -m 755 /wayland/session.sh /run/r46h-wayland-probe/session-real.sh
if [[ $# == 1 ]]; then install -m 755 /out/linux-build/r46h-shell /run/r46h-wayland-probe/usr/bin/; fi
g++ -fPIC -std=gnu++17 -O2 -Wall -Wextra -Werror /wayland/test-client.cpp -o /run/r46h-wayland-probe/usr/bin/test-client $(pkg-config --cflags --libs Qt6Quick sdl2)
mknod /dev/uinput c 10 223
timeout 100 python3 -B /wayland/test-remote.py
