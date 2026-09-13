#!/bin/sh
# Assemble an explicitly hash-bound desktop + Moonlight experiment; no installation.
set -eu
[ "$#" -eq 2 ] || { echo 'Usage: build-streaming.sh MOONLIGHT_ARM64_BINARY SHA256' >&2; exit 2; }
client=$1
expected=$2
[ "$(shasum -a 256 "$client" | cut -d ' ' -f 1)" = "$expected" ]
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
output="$source_dir/../out/.cache/r46h-shell"
stage=$(mktemp -d "$output/stream-package.XXXXXX")
trap 'rm -rf -- "$stage"' EXIT HUP INT TERM
tar -xzf "$output/r46h-shell-preview-arm64.tar.gz" -C "$stage"
install -m 755 "$client" "$stage/usr/bin/moonlight-qt"
install -m 755 "$source_dir/desktop-session.sh" "$stage/"
printf '%s\n' "$expected" > "$stage/MOONLIGHT_SHA256"
COPYFILE_DISABLE=1 tar -czf "$output/r46h-streaming-desktop-arm64.tar.gz.incoming" -C "$stage" .
mv "$output/r46h-streaming-desktop-arm64.tar.gz.incoming" "$output/r46h-streaming-desktop-arm64.tar.gz"
shasum -a 256 "$output/r46h-streaming-desktop-arm64.tar.gz"
