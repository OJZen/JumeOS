#!/bin/bash
# Fixed browser-only memory boundary inside a root-supervised transient session.
set -Eeuo pipefail
die() { echo "BROWSER_MEMORY_ERROR $*" >&2; exit 1; }
membership() { sed -n 's/^0:://p' /proc/self/cgroup; }
session_parent() {
    local current=$1
    [[ $current =~ ^/system\.slice/(r46h-wayland-probe-[0-9]+|jume-launcher)\.service/desktop$ ]] || return 1
    printf '/sys/fs/cgroup%s\n' "${current%/desktop}"
}
verify_limits() {
    local group=$1
    [[ $(cat "$group/memory.max") == 402653184 &&
       $(cat "$group/memory.swap.max") == 134217728 &&
       $(cat "$group/memory.oom.group") == 1 ]]
}
[[ $(findmnt -rn -t cgroup2 -o TARGET) == /sys/fs/cgroup ]] || die cgroup2-required
parent=$(session_parent "$(membership)") || die session-identity
group=$parent/browser
[[ -d $parent && ! -L $parent && $(stat -c %u:%g:%a "$parent") == 0:0:755 ]] || die session-owner
case ${1:-} in
--prepare)
    [[ $# == 1 && $EUID == 0 && $(id -u ark) == 1000 ]] || die arguments-or-owner
    [[ " $(cat "$parent/cgroup.controllers") " == *' memory '* ]] || die memory-controller
    # DelegateSubgroup=desktop keeps the parent empty (cgroup v2's no-internal-process rule).
    [[ -z $(cat "$parent/cgroup.procs") ]] || die parent-not-empty
    [[ ! -e $group && ! -L $group ]] || die existing-group
    printf '+memory\n' > "$parent/cgroup.subtree_control"
    mkdir -m 755 "$group"
    printf '402653184\n' > "$group/memory.max"
    printf '134217728\n' > "$group/memory.swap.max"
    printf '1\n' > "$group/memory.oom.group"
    verify_limits "$group" || die limit-readback
    # Migration requires the destination AND common ancestor's cgroup.procs.
    # No directory, controller or desktop membership file is delegated to ark.
    chown ark:ark "$parent/cgroup.procs" "$group/cgroup.procs"
    chmod 600 "$parent/cgroup.procs" "$group/cgroup.procs"
    ;;
--run)
    [[ $# -ge 2 && $EUID == 1000 ]] || die arguments-or-owner
    [[ -d $group && ! -L $group && $(stat -c %u:%g:%a "$group") == 0:0:755 ]] || die group-owner
    verify_limits "$group" || die limit-readback
    for node in memory.max memory.swap.max memory.oom.group; do
        [[ ! -w $group/$node ]] || die writable-limit
    done
    [[ ! -w $parent/desktop/cgroup.procs && ! -w $parent/cgroup.subtree_control ]] || die unsafe-delegation
    # A previous generation must have fully exited before a new browser can join.
    [[ $(sed -n 's/^populated //p' "$group/cgroup.events") == 0 ]] || die browser-still-active
    # Preserve a margin for the compositor; this is admission, not a global RAM guarantee.
    available=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    [[ $available =~ ^[0-9]+$ ]] && (( available >= 262144 )) || die memory-reserve
    printf '%s\n' "$$" > "$group/cgroup.procs"
    [[ $(membership) == "${parent#/sys/fs/cgroup}/browser" ]] || die membership-readback
    shift
    exec "$@"
    ;;
*) die arguments ;;
esac
