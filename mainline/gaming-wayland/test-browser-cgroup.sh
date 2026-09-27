#!/bin/bash
# Linux/systemd-only, real bounded memcg OOM. Does not start a GUI or change boot policy.
set -Eeuo pipefail
base=$(cd -- "$(dirname -- "$0")" && pwd -P)
if [[ ${1:-} != --inside ]]; then
    [[ $# == 0 && $EUID == 0 && $(id -u ark) == 1000 ]] || exit 2
    [[ $(findmnt -rn -t cgroup2 -o TARGET) == /sys/fs/cgroup ]] || exit 2
    available=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    [[ $available =~ ^[0-9]+$ ]] && (( available >= 655360 )) || { echo 'Need 640 MiB available; do not run alongside applications.' >&2; exit 2; }
    unit=r46h-wayland-probe-$$.service
    trap 'systemctl stop "$unit" >/dev/null 2>&1 || true' EXIT
    systemd-run --quiet --wait --pipe --collect --service-type=exec --unit="$unit" \
        -p Delegate=memory -p DelegateSubgroup=desktop -p OOMPolicy=continue \
        -p MemoryMax=448M -p MemorySwapMax=128M -p RuntimeMaxSec=25 -p TimeoutStopSec=3 \
        -p KillMode=control-group /bin/bash "$base/test-browser-cgroup.sh" --inside
    exit
fi
[[ $# == 1 && $EUID == 0 ]] || exit 2
bash "$base/browser-cgroup.sh" --prepare
parent=/sys/fs/cgroup$(sed -n 's/^0::\(.*\)\/desktop$/\1/p' /proc/self/cgroup)
[[ $parent == /sys/fs/cgroup/system.slice/r46h-wayland-probe-*.service ]]
setpriv --reuid=ark --regid=ark --init-groups -- /bin/sleep 20 &
sentinel=$!
trap 'kill "$sentinel" 2>/dev/null || true; wait "$sentinel" 2>/dev/null || true' EXIT
before=$(awk '$1=="oom_kill"{print $2}' "$parent/browser/memory.events")
set +e
setpriv --reuid=ark --regid=ark --init-groups -- /bin/bash "$base/browser-cgroup.sh" --run \
    /usr/bin/python3 -c 'import subprocess,time; subprocess.Popen(["/bin/sleep","20"],start_new_session=True); chunks=[bytearray(16*1024*1024) for _ in range(32)]; time.sleep(10)'
result=$?
set -e
[[ $result == 137 ]] || { echo "Expected memcg SIGKILL, got $result" >&2; exit 1; }
after=$(awk '$1=="oom_kill"{print $2}' "$parent/browser/memory.events")
(( after > before ))
for attempt in {1..30}; do
    [[ $(sed -n 's/^populated //p' "$parent/browser/cgroup.events") != 0 ]] || break
    sleep .1
done
[[ $(sed -n 's/^populated //p' "$parent/browser/cgroup.events") == 0 ]]
kill -0 "$sentinel"
setpriv --reuid=ark --regid=ark --init-groups -- /bin/bash "$base/browser-cgroup.sh" --run /bin/true
echo 'BROWSER_CGROUP_KERNEL_PASS: real memcg OOM, detached-child cleanup, desktop sentinel survived, relaunch passed; GUI/device acceptance separate'
