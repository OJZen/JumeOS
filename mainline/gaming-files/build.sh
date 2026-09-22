#!/bin/bash
# Optional userspace bundle; never installs anything on the host or R46H.
set -Eeuo pipefail
code=$(cd -- "$(dirname -- "$0")" && pwd -P)
mainline=$(cd -- "$code/.." && pwd -P)
out="$mainline/out/.cache/jume-files"
mkdir -p "$out/apt"
sdk=cgutman/moonlight-packaging@sha256:f25a3e2ad90b85d1a4358e2d612ed311165cddd62aa194455a5dbed844d66d69
container=$(docker create --init --entrypoint /bin/sleep -v "$mainline:/mainline:ro" -v "$out:/out" "$sdk" 3600)
trap 'docker rm -f "$container" >/dev/null' EXIT
docker start "$container" >/dev/null
docker exec "$container" bash -c 'set -e
    apt-get update -qq
    apt-get -o Dir::Cache::archives=/out/apt install -y --no-install-recommends \
        qt6-multimedia-dev=6.8.2-8 qt6-pdf-dev=6.8.2+dfsg-4 libarchive-dev=3.7.4-4+deb13u1 \
        qt6-wayland=6.8.2-4 qt6-image-formats-plugins pulseaudio=17.0+dfsg1-2+b1 ffmpeg dbus-daemon libqrencode-dev=4.1.1-2 zbar-tools
    dpkg-query -W > /out/packages.tsv' > "$out/dependencies.log" 2>&1
docker network disconnect bridge "$container"
docker network connect none "$container"
docker exec "$container" bash -c 'set -e
    cmake -S /mainline/gaming-files -B /out/build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
    cmake --build /out/build -j3
    runuser -u nobody -- python3 -B /mainline/gaming-files/test-transfer.py
    QT_QPA_PLATFORM=offscreen QT_MEDIA_BACKEND=ffmpeg LANG=C.UTF-8 dbus-run-session -- /out/build/files-check
    python3 -B /mainline/gaming-files/package.py
    bash /mainline/gaming-files/check-runtime.sh' > "$out/build-check.log" 2>&1
