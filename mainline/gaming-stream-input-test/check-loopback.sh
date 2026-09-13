#!/bin/bash
# Isolated software-rendered protocol check, never the Mac display or R46H.
set -Eeuo pipefail
[[ -f /.dockerenv && -d /out && -d /project ]] || exit 2
[[ $# == 0 || $# == 2 && $1 == --serve && $2 =~ ^[1-9][0-9]*$ && $2 -ge 10 && $2 -le 1800 ]] || exit 2
fixtures=${R46H_LOOPBACK_FIXTURES:-/out}
[[ $(sha256sum "$fixtures/sunshine-debian-trixie-arm64.deb" | cut -d ' ' -f 1) == 69736296ca56259ebde16ecbee8fb3fefb2df2880ec9789912756193fafca3ec ]]
[[ $(sha256sum /candidate.tar.gz | cut -d ' ' -f 1) == a75ba736f70fecb4eabee7334f49e5170505e5d5f5ff229814447a73ba3ca5b0 ]]
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
chmod 755 /usr/sbin/policy-rc.d
(cd "$fixtures/debs" && sha256sum --check --quiet "$fixtures/dependency-sha256.txt")
dpkg -i /existing-debs/*.deb "$fixtures"/debs/*.deb > /out/runtime-setup.log 2>&1
stage=$(mktemp -d /run/r46h-stream-loop.XXXXXX)
trap 'rm -rf -- "$stage"' EXIT
mkdir "$stage/sunshine" "$stage/client"
dpkg-deb -x "$fixtures/sunshine-debian-trixie-arm64.deb" "$stage/sunshine"
tar -xzf /candidate.tar.gz -C "$stage/client"
(cd "$stage/client" && sha256sum --check --quiet SHA256SUMS)
[[ ! -e /usr/share/sunshine ]]
ln -s "$stage/sunshine/usr/share/sunshine" /usr/share/sunshine
g++ -fPIC -std=c++17 -O2 -Wall -Wextra -Werror /project/mainline/gaming-wayland/test-client.cpp -o "$stage/test-client" $(pkg-config --cflags --libs Qt6Quick sdl2)
g++ -fPIC -std=c++17 -O2 -Wall -Wextra -Werror /project/mainline/gaming-ports/capture-x11.cpp -o "$stage/capture-x11" $(pkg-config --cflags --libs Qt6Gui)
mknod /dev/uinput c 10 223
limit=120
[[ $# == 0 ]] || limit=$(($2 + 45))
timeout "$limit" python3 -B /project/mainline/gaming-stream-input-test/loopback.py "$stage" /out "$@"
