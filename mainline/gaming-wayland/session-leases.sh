#!/bin/bash
# Internal transient-unit hook: restore every requested lease, even if one fails.
set -Eeuo pipefail
[[ $# == 4 && ( $1 == --acquire || $1 == --restore ) && $2 =~ ^r46h-wayland-probe-[0-9]+\.service$ && ( $3 == 0 || $3 == 1 ) && ( $4 == 0 || $4 == 1 ) && $EUID == 0 ]] || exit 2
base=$(cd -- "$(dirname -- "$0")" && pwd -P)
[[ $base == /run/r46h-wayland-probe ]] || exit 2
operation=$1 unit=$2 ports=$3 device=$4
if [[ $operation == --acquire ]]; then
    if (( device )); then /bin/bash "$base/device-lease.sh" --acquire "$unit"; fi
    if (( ports )); then /bin/bash "$base/runtime-lease.sh" --acquire "$unit"; fi
else
    result=0
    if (( ports )); then /bin/bash "$base/runtime-lease.sh" --release "$unit" || result=1; fi
    if (( device )); then /bin/bash "$base/device-lease.sh" --restore "$unit" || result=1; fi
    exit "$result"
fi
