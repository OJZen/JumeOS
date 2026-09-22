#!/bin/bash
# Container-only package/PCM proof. No real disk mounts, audio devices or network.
set -Eeuo pipefail
[[ -f /.dockerenv && -f /out/jume-files-arm64.tar.gz ]] || exit 2
[[ $(sha256sum /out/jume-files-arm64.tar.gz | cut -d ' ' -f 1) == "$(cat /out/runtime.sha256)" ]]
stage=$(mktemp -d /out/files-runtime.XXXXXX)
runtime=$(mktemp -d /run/files-check.XXXXXX)
server= recorder=
cleanup() {
    [[ -z $recorder ]] || kill "$recorder" 2>/dev/null || true
    [[ -z $recorder ]] || wait "$recorder" 2>/dev/null || true
    [[ -z $server ]] || kill "$server" 2>/dev/null || true
    [[ -z $server ]] || wait "$server" 2>/dev/null || true
    rm -rf -- "$stage" "$runtime"
}
trap cleanup EXIT
tar -xzf /out/jume-files-arm64.tar.gz -C "$stage"
(cd "$stage" && sha256sum --check --quiet SHA256SUMS)
runuser -u nobody -- env JUME_TRANSFER_MODULE="$stage/usr/share/jume-files/transfer_server.py" \
    python3 -B /mainline/gaming-files/test-transfer.py > /out/transfer-http-check.log 2>&1
chown nobody:nogroup "$runtime"
install -d -o nobody -g nogroup "$runtime/images"
export XDG_RUNTIME_DIR="$runtime" PULSE_RUNTIME_PATH="$runtime" PULSE_STATE_PATH="$runtime" PULSE_CONFIG_PATH="$runtime"
export PULSE_SERVER="unix:$runtime/native" PULSE_SINK=files_test
export LD_LIBRARY_PATH="$stage/usr/lib/aarch64-linux-gnu:$stage/usr/lib/aarch64-linux-gnu/libproxy" QT_PLUGIN_PATH="$stage/usr/lib/aarch64-linux-gnu/qt6/plugins"
runuser -u nobody -- "$stage/usr/bin/pulseaudio" -n --daemonize=no --exit-idle-time=-1 --use-pid-file=no --disable-shm=yes \
    --dl-search-path="$stage/usr/lib/aarch64-linux-gnu/jume-audio" \
    --load="module-native-protocol-unix socket=$runtime/native auth-anonymous=1 auth-cookie-enabled=0" \
    --load="module-null-sink sink_name=files_test channels=2 rate=48000 norewinds=1" > /out/audio-server.log 2>&1 &
server=$!
for attempt in {1..60}; do [[ ! -S $runtime/native ]] || break;kill -0 "$server";sleep .05;done
[[ -S $runtime/native ]]
runuser -u nobody -- pactl list sinks > /out/audio-sink.log
runuser -u nobody -- pactl list sources > /out/audio-source.log
runuser -u nobody -- parec --device=files_test.monitor --format=s16le --rate=48000 --channels=2 --latency-msec=20 > "$runtime/pcm" 2>/out/audio-capture.log &
recorder=$!
runuser -u nobody -- env QT_QPA_PLATFORM=offscreen QT_MEDIA_BACKEND=ffmpeg LANG=C.UTF-8 JUME_FILES_AUDIO_TEST=1 \
    JUME_FILES_CAPTURE_DIR="$runtime/images" \
    JUME_FILES_FONT="$stage/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf" \
    dbus-run-session -- /out/build/files-check > /out/runtime-check.log 2>&1
mkdir -p /out/images
cp "$runtime/images/"*.png /out/images/
# norewinds bounds this synthetic sink to 50 ms; drain its monitor tail.
sleep .3
kill "$recorder";wait "$recorder" || true;recorder=
python3 -B - "$runtime/pcm" <<'PY'
import array,pathlib,sys
data=pathlib.Path(sys.argv[1]).read_bytes()
values=array.array('h',data[:len(data)//2*2])
assert len(values)>4800 and max(abs(v) for v in values)>500, f'No real PCM reached the private monitor: samples={len(values)} peak={max((abs(v) for v in values),default=0)}'
print('FILES_RUNTIME_PASS native_widgets_pdf_video_real_pcm usb_physical=UNTESTED')
PY
# Main executable must also start as a non-root user with its own private state.
runuser -u nobody -- env QT_QPA_PLATFORM=offscreen LANG=C.UTF-8 SDL_NO_SIGNAL_HANDLERS=1 timeout --preserve-status --kill-after=1 2 \
    "$stage/usr/bin/jume-files" --state-dir "$runtime/state" --directory "$runtime" --windowed > /out/startup.log 2>&1 &
client=$!
sleep .3
kill -0 "$client"
status=0;wait "$client" || status=$?
[[ $status == 143 ]] # Bounded test shutdown, not a native startup failure.
