#!/bin/bash
set -Eeuo pipefail

PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly FEATURE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly REPO=$(cd -- "$FEATURE_DIR/../.." && pwd -P)
readonly OUTPUT=$REPO/mainline/out/r46h-gaming-remote-input-v0.1
readonly DOCKER=/usr/local/bin/docker
readonly BUILDER=sha256:3686fd20408cf746c1171e9345fd6c842a71f87e589f691b2455435b3bdd141a
readonly EXPECTED_BINARY_SHA256=9907972995127792b75f0cf9922c3d750e8a06437b3d4d026f4a1db614f0232c

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ -x $DOCKER ]] || die 'Docker CLI is unavailable'
identity=$($DOCKER image inspect --format '{{.Id}} {{.Architecture}} {{.Os}}' "$BUILDER")
[[ $identity == "$BUILDER arm64 linux" ]] || die 'builder identity mismatch'
install -d -m 0755 "$OUTPUT"
expected=$'README.md\nSHA256SUMS\ninstall.sh\nr46h-remote-input\nr46h-remote-input.sudoers\nr46h-screenshot-ssh\nrollback.sh'
if [[ -n $(LC_ALL=C /bin/ls -1A "$OUTPUT" | sort | comm -23 - <(printf '%s\n' "$expected")) ]]; then
  die 'unexpected output member'
fi

$DOCKER run --rm --network none --pull never --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=32m \
  -v "$FEATURE_DIR:/src:ro" -v "$OUTPUT:/out:rw" \
  --entrypoint /bin/sh "$BUILDER" -c '
    set -eu
    umask 022
    gcc -std=c11 -O2 -fPIE -pie -D_FORTIFY_SOURCE=3 \
      -fstack-protector-strong -Wall -Wextra -Werror -Wformat=2 \
      -Wshadow -Wstrict-prototypes -Wl,-z,relro,-z,now \
      -Wl,--build-id=none -ffile-prefix-map=/src=. \
      -fdebug-prefix-map=/src=. -o /out/.r46h-remote-input.tmp \
      /src/r46h-remote-input.c
    strip --strip-unneeded /out/.r46h-remote-input.tmp
    chmod 0755 /out/.r46h-remote-input.tmp
    mv -f /out/.r46h-remote-input.tmp /out/r46h-remote-input
    /out/r46h-remote-input --self-test
    test "$(/out/r46h-remote-input --version)" = r46h-gaming-remote-input-v0.1
  '

binary_sha256=$(sha256sum "$OUTPUT/r46h-remote-input" | awk '{print $1}')
[[ $binary_sha256 == "$EXPECTED_BINARY_SHA256" ]] || die "binary SHA-256 mismatch: $binary_sha256"
$DOCKER run --rm --network none --pull never --read-only \
  -v "$OUTPUT:/out:ro" --entrypoint /bin/sh "$BUILDER" -c '
    set -eu
    readelf -h /out/r46h-remote-input | grep -Fq "Class:                             ELF64"
    readelf -h /out/r46h-remote-input | grep -Fq "Machine:                           AArch64"
    readelf -h /out/r46h-remote-input | grep -Fq "Type:                              DYN (Position-Independent Executable file)"
    dependencies=$(readelf -d /out/r46h-remote-input |
      sed -n "s/.*Shared library: \[\(.*\)\]/\1/p" | sort)
    test "$dependencies" = "$(printf "%s\n" ld-linux-aarch64.so.1 libc.so.6)"
  '

for name in README.md install.sh r46h-remote-input.sudoers r46h-screenshot-ssh rollback.sh; do
  install -m 0644 "$FEATURE_DIR/$name" "$OUTPUT/$name"
done
(cd "$OUTPUT" && sha256sum README.md install.sh r46h-remote-input \
  r46h-remote-input.sudoers r46h-screenshot-ssh rollback.sh > SHA256SUMS)
printf 'R46H_REMOTE_INPUT_PAYLOAD result=pass output=%s binary_sha256=%s\n' \
  "$OUTPUT" "$binary_sha256"
