#!/usr/bin/env python3
"""Compile the real native formatter/protocol and test bounded pipe delivery."""
from pathlib import Path
import json
import re
import shlex
import subprocess
import sys

source, out = map(Path, sys.argv[1:])
out.mkdir(parents=True, exist_ok=True)
video = source / 'app/streaming/video'
cpp = (video / 'ffmpeg.cpp').read_text()
formatter = cpp[cpp.index('static QJsonObject r46hVideoStats('):cpp.index('void FFmpegVideoDecoder::addVideoStats')]
fields = re.search(r'typedef struct _VIDEO_STATS \{.*?\} VIDEO_STATS, \*PVIDEO_STATS;', (video / 'decoder.h').read_text(), re.S).group()
assert 'm_ReportStats = !testOnly' in cpp and 'LiGetPendingAudioDuration()' in cpp
fixture = out / 'stats-check.cpp'
fixture.write_text('''#include "streamstats.h"
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <limits>
''' + fields + '\n' + formatter + '''
int main() {
    VIDEO_STATS stats{};
    stats.receivedFps=60; stats.decodedFps=59; stats.renderedFps=58;
    stats.totalFrames=100; stats.decodedFrames=50; stats.renderedFrames=40;
    stats.networkDroppedFrames=2; stats.pacerDroppedFrames=1;
    stats.totalDecodeTime=100; stats.totalPacerTime=120; stats.totalRenderTime=160;
    stats.lastRtt=12; stats.totalHostProcessingLatency=500; stats.framesWithHostProcessingLatency=10;
    auto value=r46hVideoStats(stats, 15);
    assert(value["networkDropPercent"].toDouble()==2 && value["pacingDropPercent"].toDouble()==2);
    assert(value["decodeMs"].toDouble()==2 && value["queueMs"].toDouble()==3 && value["renderCallMs"].toDouble()==4);
    assert(value["hostProcessingMs"].toDouble()==5 && value["audioNetworkQueueMs"].toDouble()==15);
    auto packet=StreamStats::encode(value); assert(StreamStats::parse(packet)==value);
    auto empty=r46hVideoStats(VIDEO_STATS{}, 0);
    assert(empty["decodeMs"].toDouble()==-1 && empty["rttMs"].toDouble()==-1);
    stats.renderedFps=std::numeric_limits<float>::infinity();
    assert(r46hVideoStats(stats,0)["renderedFps"].toDouble()==-1);
    value["address"]="private-fixture"; assert(StreamStats::parse(StreamStats::encode(value)).isEmpty());
    value.remove("address"); value["rttMs"]="private-fixture";
    assert(StreamStats::parse(StreamStats::encode(value)).isEmpty());
    assert(StreamStats::parse(QByteArray(9000,'x')).isEmpty());
    int descriptors[2]; assert(pipe(descriptors)==0);
    const int saved=dup(STDOUT_FILENO); assert(saved>=0);
    assert(dup2(descriptors[1],STDOUT_FILENO)>=0); close(descriptors[1]);
    assert(StreamStats::preparePipe()); StreamStats::send(packet);
    char received[4096]; auto bytes=read(descriptors[0],received,sizeof(received));
    assert(QByteArray(received,int(bytes))==packet);
    const QByteArray fill(4096,'x');
    while(write(STDOUT_FILENO,fill.constData(),fill.size())>0) {}
    assert(errno==EAGAIN); StreamStats::send(packet); // Must not block on a full consumer.
    close(descriptors[0]); StreamStats::send(packet); // Must not die with SIGPIPE.
    assert(dup2(saved,STDOUT_FILENO)>=0); close(saved);
    puts("MOONLIGHT_STATS_PASS: actual formatter, missing values, numeric-only schema, full/closed pipe safety");
}
''')
flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
subprocess.run(['g++', '-std=c++17', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror', '-I'+str(video),
                str(fixture), '-o', str(out / 'stats-check'), *flags], check=True)
result = subprocess.run([str(out / 'stats-check')], capture_output=True, text=True, check=True, timeout=5)
(out / 'result.json').write_text(json.dumps({'status': 'NATIVE_STATS_FORMAT_PIPE_HOST_PASS',
    'boundary': 'Real formatter/protocol with controlled counters; no streaming, decoded video or audio-output proof.'}, indent=2)+'\n')
print(result.stdout, end='')
