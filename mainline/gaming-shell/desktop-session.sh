#!/bin/sh
# One cgroup owns this supervisor, the desktop and its streaming child.
set -u
case $# in
  1) ;;
  2) [ "$2" = --attended ] || exit 2 ;;
  3) [ "$2" = --remote ] && [ -d "$3" ] && [ ! -L "$3" ] || exit 2 ;;
  *) exit 2 ;;
esac
client_hash=$1
kind=stream
scene=neo
[ "$client_hash" != native ] || kind=native
if [ "$client_hash" = ports ]; then kind=native; scene=ports; fi
resume=0
if [ "$kind" = stream ]; then
  case "$client_hash" in *[!0-9a-f]*|'') exit 2;; esac
  [ "${#client_hash}" -eq 64 ] || exit 2
fi
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
client="$base/usr/bin/moonlight-qt"
[ "$kind" = native ] || [ -x "$client" ] || exit 2
gui_seconds=290
attended=0
control_dir=
if [ "${2:-}" = --attended ]; then gui_seconds=1800; attended=1; fi
if [ "${2:-}" = --remote ]; then gui_seconds=1800; control_dir=$3; fi
umask 077
while :; do
  if [ "$kind" = native ]; then
    set -- --fullscreen --scene "$scene" --quit-after "$gui_seconds" --native-handoff
    [ "$resume" != 1 ] || set -- "$@" --resume-native
  else
    set -- --fullscreen --scene streaming --quit-after "$gui_seconds" \
      --moonlight-client "$client" --moonlight-sha256 "$client_hash" --stream-handoff
  fi
  if [ -n "$control_dir" ]; then set -- "$@" --control-dir "$control_dir" --test-input-capture; fi
  "$base/shell-client.sh" "$@"
  result=$?
  if [ "$kind" = native ]; then [ "$result" -eq 79 ] || exit "$result"; else [ "$result" -eq 75 ] || exit "$result"; fi
  # The GUI has exited and released EGLFS/DRM before this process opens the client.
  if [ "$attended" = 1 ]; then set -- --attended; else set --; fi
  if [ "$kind" = native ]; then
    R46H_SHELL_LOG=0 "$base/shell-client.sh" --native-worker "$@"
  else
    R46H_SHELL_LOG=0 SDL_VIDEODRIVER=kmsdrm SDL_AUDIODRIVER=alsa \
      "$base/shell-client.sh" --stream-worker --moonlight-client "$client" --moonlight-sha256 "$client_hash" "$@"
  fi
  result=$?
  if [ "$kind" = native ]; then printf 'NATIVE_WORKER_END status=%s\n' "$result"; else printf 'STREAM_WORKER_END status=%s\n' "$result"; fi
  [ "$result" -ne 2 ] || exit 2
  resume=1
  # The next desktop reads only the safe status record, never the client log.
done
