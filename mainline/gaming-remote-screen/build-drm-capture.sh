#!/bin/bash
set -Eeuo pipefail

PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly FEATURE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly REPO=$(cd -- "$FEATURE_DIR/../.." && pwd -P)
readonly OUTPUT_DIR=$REPO/mainline/out/r46h-gaming-remote-screen-v0.2
readonly OUTPUT=$OUTPUT_DIR/r46h-drm-capture
readonly SOURCE=$FEATURE_DIR/r46h-drm-capture.c
readonly DOCKER=/usr/local/bin/docker
readonly BUILDER=sha256:3686fd20408cf746c1171e9345fd6c842a71f87e589f691b2455435b3bdd141a
readonly EXPECTED_SHA256=77f22181289edd701001fd6570a49afbfde277417e3769a693d1dd335cad324e

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  printf 'usage: %s build|validate\n' "${BASH_SOURCE[0]}"
}

verify_builder() {
  local identity

  [[ -x "$DOCKER" ]] || die 'Docker CLI is unavailable'
  identity=$($DOCKER image inspect --format '{{.Id}} {{.Architecture}} {{.Os}}' "$BUILDER")
  [[ "$identity" == "$BUILDER arm64 linux" ]] || die 'builder identity mismatch'
}

validate_output() {
  local digest

  [[ -f "$OUTPUT" && ! -L "$OUTPUT" && -x "$OUTPUT" ]] || die 'capture output is unavailable'
  digest=$(sha256sum "$OUTPUT" | awk '{print $1}')
  [[ "$digest" == "$EXPECTED_SHA256" ]] || die 'capture output SHA-256 mismatch'
  $DOCKER run --rm --network none --pull never --read-only \
    -v "$OUTPUT_DIR:/out:ro" --entrypoint /bin/sh "$BUILDER" -c '
      set -eu
      readelf -h /out/r46h-drm-capture | grep -Fq "Class:                             ELF64"
      readelf -h /out/r46h-drm-capture | grep -Eq "Data:.*little endian"
      readelf -h /out/r46h-drm-capture | grep -Fq "Type:                              DYN (Position-Independent Executable file)"
      readelf -h /out/r46h-drm-capture | grep -Fq "Machine:                           AArch64"
      dependencies=$(readelf -d /out/r46h-drm-capture |
        sed -n "s/.*Shared library: \[\(.*\)\]/\1/p" | sort)
      test "$dependencies" = "$(printf "%s\n" ld-linux-aarch64.so.1 libc.so.6 libz.so.1)"
    '
  printf 'PASS: R46H DRM capture artifact %s\n' "$digest"
}

[[ $# == 1 ]] || { usage >&2; exit 2; }
verify_builder
case $1 in
  build)
    [[ -f "$SOURCE" && ! -L "$SOURCE" ]] || die 'capture source is unavailable'
    install -d -m 0755 "$OUTPUT_DIR"
    $DOCKER run --rm --network none --pull never --read-only \
      --tmpfs /tmp:rw,nosuid,nodev,noexec,size=64m \
      -v "$FEATURE_DIR:/src:ro" -v "$OUTPUT_DIR:/out:rw" \
      --entrypoint /bin/sh "$BUILDER" -c '
        set -eu
        umask 022
        gcc -std=c11 -O2 -fPIE -pie -D_FORTIFY_SOURCE=3 \
          -fstack-protector-strong -Wall -Wextra -Werror -Wformat=2 \
          -Wshadow -Wstrict-prototypes -Wl,-z,relro,-z,now \
          -Wl,--build-id=none -ffile-prefix-map=/src=. \
          -fdebug-prefix-map=/src=. -o /out/.r46h-drm-capture.tmp \
          /src/r46h-drm-capture.c -lz -ldl
        strip --strip-unneeded /out/.r46h-drm-capture.tmp
        chmod 0755 /out/.r46h-drm-capture.tmp
        mv -f /out/.r46h-drm-capture.tmp /out/r46h-drm-capture
      '
    validate_output
    ;;
  validate) validate_output ;;
  *) usage >&2; exit 2 ;;
esac
