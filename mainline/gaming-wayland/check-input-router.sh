#!/bin/bash
# Container-only driver; all device nodes below are synthetic and local to it.
set -Eeuo pipefail
[[ -f /.dockerenv && -d /src && -d /out ]] || exit 2
g++ -std=c++17 -Wall -Wextra -Werror -O2 /src/input-router.cpp -o /out/input-router
g++ -std=c++17 -Wall -Wextra -Werror -O2 /src/test-input-policy.cpp -o /out/test-input-policy
/out/test-input-policy
[[ $(cat /sys/class/misc/uinput/dev) == 10:223 ]]
mknod /dev/uinput c 10 223
timeout 30 python3 -B /src/test-input-router.py /out/input-router
