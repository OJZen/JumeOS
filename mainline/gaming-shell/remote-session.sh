#!/bin/bash
# Internal entry point of probe-r46h.sh --remote. One cgroup owns SSH and the UI.
set -Eeuo pipefail
[[ ( $# == 2 || $# == 3 && ( $3 =~ ^[0-9a-f]{64}$ || $3 == native || $3 == ports ) || $# == 4 && $3 == wayland ) && $EUID == 0 ]] || exit 2
shared=0
[[ $# != 4 ]] || shared=1
listen=$1
peer=$2
for address in "$listen" "$peer"; do
  [[ $address =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || exit 2
  IFS=. read -r -a octets <<< "$address"
  for octet in "${octets[@]}"; do (( 10#$octet <= 255 )) || exit 2; done
done
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
if (( shared )); then
  [[ $base == /run/r46h-wayland-probe && $4 =~ ^/run/r46h-wayland-probe/state/session\.[[:alnum:]]+$ ]] || exit 2
  output=$4
  [[ ! -L $output && $(readlink -f "$output") == "$output" && $(stat -c %u:%a "$output") == 1000:700 ]] || exit 2
else
  [[ $base == /run/r46h-shell-probe ]] || exit 2
fi
ip -4 -o address show | awk '{split($4,a,"/");print a[1]}' | grep -Fxq "$listen"
[[ -x /usr/sbin/sshd && -f /etc/ssh/ssh_host_ed25519_key.pub ]]
read -r key_type key_blob _ < "$base/remote-client.pub"
[[ $key_type == ssh-ed25519 && $key_blob =~ ^[A-Za-z0-9+/=]+$ ]]
[[ $(wc -l < "$base/remote-client.pub") == 1 ]]
ssh-keygen -lf "$base/remote-client.pub" >/dev/null
umask 077
if (( shared )); then
  control="$output/control"
  [[ ! -e $control && ! -L $control ]] || exit 1
  install -d -o ark -g ark -m 700 "$control"
else
  install -d -o ark -g ark -m 700 "$base/state"
  control=$(mktemp -d "$base/state/control.XXXXXX")
  chown ark:ark "$control"
fi
runtime=$(mktemp -d "$base/remote-ssh.XXXXXX")
chmod 755 "$runtime"
install -d -o ark -g ark -m 700 "$runtime/call-state"
sshd_pid=
cleanup() {
  result=$?
  trap - EXIT
  if [[ -n $sshd_pid ]]; then kill "$sshd_pid" 2>/dev/null || true; wait "$sshd_pid" 2>/dev/null || true; fi
  rm -rf -- "$control" "$runtime"
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
printf '%s %s\n' "$key_type" "$key_blob" > "$runtime/authorized_keys"
chmod 644 "$runtime/authorized_keys"
cat > "$runtime/sshd_config" <<CONFIG
Port 22222
ListenAddress $listen
HostKey /etc/ssh/ssh_host_ed25519_key
PidFile $runtime/sshd.pid
AuthorizedKeysFile $runtime/authorized_keys
StrictModes yes
AllowUsers ark@$peer
AuthenticationMethods publickey
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
DisableForwarding yes
PermitTTY no
PermitUserRC no
UsePAM no
MaxSessions 1
MaxAuthTries 2
LoginGraceTime 10
LogLevel ERROR
ForceCommand /usr/bin/env R46H_SHELL_STATE_DIR=$runtime/call-state $base/shell-client.sh --control-call --control-dir $control
CONFIG
/usr/sbin/sshd -t -f "$runtime/sshd_config"
# Read this public identity over the verified serial console before using SSH.
host_key=$(cut -d ' ' -f 1,2 /etc/ssh/ssh_host_ed25519_key.pub)
printf '[%s]:22222 %s\n' "$listen" "$host_key" > "$base/remote-known-hosts"
printf 'boot_id=%s\nlisten=%s\npeer=%s\n' "$(cat /proc/sys/kernel/random/boot_id)" "$listen" "$peer" > "$base/remote-identity"
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256 >> "$base/remote-identity"
/usr/sbin/sshd -D -e -f "$runtime/sshd_config" > "$base/remote-ssh.log" 2>&1 &
sshd_pid=$!
sleep 0.2
kill -0 "$sshd_pid"
printf 'REMOTE_UI_BEGIN port=22222 control=application-actions lifetime=preview\n' > "$base/remote-session.log"
if (( shared )); then
  "$base/session.sh" seat "$output" handheld
elif [[ $# == 3 ]]; then
  /usr/sbin/runuser -u ark -- /usr/bin/env R46H_SHELL_LOG=1 \
    "$base/desktop-session.sh" "$3" --remote "$control"
else
  /usr/sbin/runuser -u ark -- /usr/bin/env R46H_SHELL_LOG=1 \
    "$base/shell-client.sh" --fullscreen --quit-after 1800 --control-dir "$control" --test-input-capture
fi
