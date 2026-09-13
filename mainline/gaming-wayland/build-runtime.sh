#!/bin/sh
# Host preparation only; dependencies install inside a disposable container.
set -eu
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
workspace=$(CDPATH= cd -- "$source_dir/../.." && pwd -P)
output="$workspace/mainline/out/.cache/r46h-wayland"
mkdir -p "$output/evidence" "$output/tmp" "$output/deb-cache"
container=$(docker create --network bridge --entrypoint /bin/sleep \
  -v "$workspace/mainline:/project:ro" -v "$output:/out" \
  cgutman/moonlight-packaging@sha256:f25a3e2ad90b85d1a4358e2d612ed311165cddd62aa194455a5dbed844d66d69 1800)
trap 'docker rm -f "$container" >/dev/null' EXIT HUP INT TERM
docker start "$container" >/dev/null
docker exec "$container" /bin/bash -c '
set -eu
export TMPDIR=/out/tmp
apt-get update
apt-get install -y --no-install-recommends weston=14.0.2-1 libweston-14-0=14.0.2-1 \
  qt6-wayland=6.8.2-4 libqt6waylandclient6=6.8.2-4 seatd=0.9.1-1 libseat1=0.9.1-1
cd /out/deb-cache
apt-get download weston=14.0.2-1 libweston-14-0=14.0.2-1 qt6-wayland=6.8.2-4 \
  libqt6waylandclient6=6.8.2-4 seatd=0.9.1-1 libseat1=0.9.1-1
dpkg-query -W > /out/evidence/packages.txt
' > "$output/evidence/setup.log" 2>&1
docker network disconnect bridge "$container"
docker network connect none "$container"
docker exec "$container" env PYTHONDONTWRITEBYTECODE=1 TMPDIR=/out/tmp \
  python3 -B /project/gaming-wayland/build-in-container.py
