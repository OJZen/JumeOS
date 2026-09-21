#!/bin/sh
# Standalone, optional runtime. Does not change an image, device or accepted shell.
set -eu
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
workspace=$(CDPATH= cd -- "$source_dir/../.." && pwd -P)
output="$workspace/mainline/out/.cache/jume-browser"
shell_runtime="$workspace/mainline/out/.cache/r46h-shell"
sdk=cgutman/moonlight-packaging@sha256:f25a3e2ad90b85d1a4358e2d612ed311165cddd62aa194455a5dbed844d66d69
[ -f "$shell_runtime/r46h-shell-preview-arm64.tar.gz" ] || exit 2
mkdir -p "$output/tmp" "$output/apt"
shasum -a 256 "$shell_runtime/r46h-shell-preview-arm64.tar.gz" > "$output/base.sha256"
# Mount sources together so the existing Qt controls/input remain the only owner.
container=$(docker create --init --network bridge --entrypoint /bin/sleep \
    -v "$source_dir:/src:ro" -v "$workspace/mainline/gaming-shell:/gaming-shell:ro" \
    -v "$output:/out" -v "$shell_runtime:/shell-runtime:ro" "$sdk" 3600)
trap 'docker rm -f "$container" >/dev/null' EXIT HUP INT TERM
docker start "$container" >/dev/null
docker exec "$container" bash -c '
    set -eu
    install -m 644 /src/backports.sources /etc/apt/sources.list.d/jume-browser-backports.sources
    apt-get update -qq
    apt-get -t trixie-backports -o Dir::Cache::archives=/out/apt install -y --no-install-recommends \
        qt6-webengine-dev=6.10.2+dfsg-3~bpo13+1 qml6-module-qtwebengine=6.10.2+dfsg-3~bpo13+1 qt6-wayland
    # These are already installed in the SDK, but absent from the R46H/base bundle.
    apt-get -o Dir::Cache::archives=/out/apt install -y --download-only --reinstall \
        libxcomposite1 libxdamage1 libxtst6
    dpkg-query -W > /out/packages.tsv
' > "$output/dependencies.log" 2>&1
docker network disconnect bridge "$container"
docker network connect none "$container"
docker exec "$container" bash /src/package.sh
git -C "$workspace" rev-parse HEAD > "$output/source-revision.txt"
git -C "$workspace" diff --binary -- mainline/gaming-shell > "$output/shell-integration.patch"
# Includes uncommitted browser sources; a preview must not claim clean provenance.
COPYFILE_DISABLE=1 tar -czf "$output/browser-source.tar.gz" -C "$source_dir" .
shasum -a 256 "$output/jume-browser-arm64.tar.gz" "$output/browser-source.tar.gz"
