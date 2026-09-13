#!/bin/bash
# Temporary Sunshine on the current Mac's Docker VM, displaying only the test app.
set -Eeuo pipefail
[[ $# == 1 || $# == 2 ]] || { echo 'Usage: run-linux-host.sh LOCAL_IPV4 [SECONDS:10..1800]' >&2; exit 2; }
listen=$1 seconds=${2:-900}
[[ $seconds =~ ^[1-9][0-9]*$ && $seconds -ge 10 && $seconds -le 1800 ]] || exit 2
python3 -B - "$listen" <<'PY'
import ipaddress,re,subprocess,sys
address=ipaddress.IPv4Address(sys.argv[1])
assert not address.is_multicast and not address.is_unspecified
interfaces=subprocess.check_output(['ifconfig'],text=True)
assert str(address) in re.findall(r'\binet (\d+\.\d+\.\d+\.\d+)\b',interfaces), 'Use a currently assigned local IPv4 address'
PY
repo=$(cd -- "$(dirname -- "$0")/../.." && pwd -P)
cache=$repo/mainline/out/.cache
fixtures=$cache/r46h-stream-loopback
[[ -f $fixtures/dependency-sha256.txt ]]
output=$(mktemp -d "$fixtures/host.XXXXXX")
ports=()
for port in 47984 47989 48010; do ports+=(-p "$listen:$port:$port/tcp"); done
for port in 47998 47999 48000 48010; do ports+=(-p "$listen:$port:$port/udp"); done
terminal=(-i); [[ ! -t 0 ]] || terminal+=(-t)
echo "Temporary host evidence: $output"
exec docker run --rm --init "${terminal[@]}" --memory 2048m --cpus 4 --pids-limit 256 \
  --device-cgroup-rule 'c 10:223 rwm' --device-cgroup-rule 'c 13:* rwm' "${ports[@]}" \
  --entrypoint /bin/bash -e R46H_LOOPBACK_FIXTURES=/fixtures \
  -v "$repo/mainline/gaming-stream-input-test:/project/mainline/gaming-stream-input-test:ro" \
  -v "$repo/mainline/gaming-wayland:/project/mainline/gaming-wayland:ro" \
  -v "$repo/mainline/gaming-ports:/project/mainline/gaming-ports:ro" \
  -v "$fixtures:/fixtures:ro" -v "$output:/out" \
  -v "$cache/r46h-ports-backend-20260910/game-debs:/existing-debs:ro" \
  -v "$cache/r46h-compositor-20260910/r28/r46h-handheld-desktop-arm64.tar.gz:/candidate.tar.gz:ro" \
  cgutman/moonlight-packaging@sha256:f25a3e2ad90b85d1a4358e2d612ed311165cddd62aa194455a5dbed844d66d69 \
  /project/mainline/gaming-stream-input-test/check-loopback.sh --serve "$seconds"
