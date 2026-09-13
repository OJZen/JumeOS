#!/bin/bash
# Shared package assembly only; never an installer for the host or target filesystem.
set -Eeuo pipefail
[[ -f /.dockerenv && $# == 1 && -d $1 && ! -L $1 ]] || exit 2
case "$1" in /run/*|/out/*) ;; *) exit 2;; esac
stage=$1
code=/project/mainline/gaming-ports
tests=/project/mainline/tests
python3 -B "$code/prepare-native.py" /native-debs --check
mkdir -p "$stage/usr/share/r46h/portmaster" "$stage/usr/share/r46h/ports" "$stage/usr/lib/r46h-ports" "$stage/usr/share/doc/r46h-ports"
tar -xzf /portmaster-backend.tar.gz -C "$stage/usr/share/r46h/portmaster"
python3 -B - "$code/backend-lock.json" "$stage/usr/share/r46h/portmaster/SOURCE.json" <<'PY'
import json,sys
assert json.load(open(sys.argv[1])) == json.load(open(sys.argv[2]))
PY
install -m 644 "$code/manager.py" "$code/local_port.py" "$stage/usr/share/r46h/ports/"
install -m 755 "$code/runtime-lease.sh" "$stage/"
gcc -shared -fPIC -O2 -Wall -Wextra -Werror -Wl,-z,relro,-z,now \
  "$code/mono-compat.c" -o "$stage/usr/lib/r46h-ports/libmono-compat.so" -ldl -pthread
[[ $(sha256sum /gta-source/re3 | cut -d ' ' -f 1) == c7f9d60c65148228523c4c12f7178be295f3aa8f6278a69ecca1e735c0ff085d ]]
[[ $(sha256sum /gta-source/reVC | cut -d ' ' -f 1) == 2ad92a8b22d963d8f7104a1a8ea40a0f6174e10b451e58373bb0021347dcd005 ]]
install -m 755 /gta-source/re3 /gta-source/reVC "$stage/usr/lib/r46h-ports/"
python3 -B "$tests/test-mono-compat.py" --library "$stage/usr/lib/r46h-ports/libmono-compat.so"
native=$(mktemp -d /run/r46h-native-libraries.XXXXXX)
trap 'rm -rf -- "$native"' EXIT
for deb in /native-debs/*.deb; do dpkg-deb -x "$deb" "$native"; done
mkdir -p "$stage/usr/bin" "$stage/usr/lib"
install -m 755 "$native/usr/bin/python3.13" "$stage/usr/bin/"
cp -a "$native/usr/lib/python3.13" "$stage/usr/lib/"
cp -a "$native/usr/share/doc/"{python3.13-minimal,libpython3.13-minimal,libpython3.13-stdlib} "$stage/usr/share/doc/r46h-ports/"
env -u LD_LIBRARY_PATH -u PYTHONHOME -u PYTHONPATH "$stage/usr/bin/python3.13" -I -B "$tests/test-port-python.py"
env -u LD_LIBRARY_PATH -u PYTHONHOME -u PYTHONPATH "$stage/usr/bin/python3.13" -I -B "$stage/usr/share/r46h/ports/local_port.py" --help > /dev/null
cp -a "$native/usr/lib/aarch64-linux-gnu/"libopenal.so* "$native/usr/lib/aarch64-linux-gnu/"libmpg123.so* "$stage/usr/lib/r46h-ports/"
cp -a "$native/usr/share/doc/libopenal1" "$native/usr/share/doc/libmpg123-0t64" "$stage/usr/share/doc/r46h-ports/"
mkdir -p /project/mainline/out/.cache
python3 -B "$tests/test-portmaster-manager.py" --runtime "$stage/usr/share/r46h/portmaster"
