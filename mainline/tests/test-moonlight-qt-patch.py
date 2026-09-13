#!/usr/bin/env python3
"""Compile the patched predicates/writeBuffer and execute the QML handlers.

Run inside the pinned ARM64 builder; SOURCE is the patched upstream checkout.
The optional Annex-B fixture is artificial VideoToolbox output, never a capture.
"""
from pathlib import Path
import argparse
import json
import re
import shlex
import subprocess


def function(source, declaration):
    start = source.index(declaration)
    return source[start:source.index('\n}', start) + 2]


def run(*args):
    return subprocess.run(args, check=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--fixture', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    video = (source / 'app/streaming/video/ffmpeg.cpp').read_text()
    gamepad = (source / 'app/streaming/input/gamepad.cpp').read_text()
    start = video.index('if ((params->videoFormat & VIDEO_FORMAT_MASK_H264)')
    sps_condition = video[start + 4:video.index(' {', start) - 1]
    end = gamepad.index('"Detected quit gamepad button combo"')
    start = gamepad.rindex('if (', 0, end)
    quit_condition = gamepad[start + 4:gamepad.index(' {', start) - 1]
    write_buffer = function(video, 'void FFmpegVideoDecoder::writeBuffer(')
    stream_qml = (source / 'app/gui/StreamSegue.qml').read_text()
    cli_qml = (source / 'app/gui/CliStartStreamSegue.qml').read_text()

    def qml_function(text, name):
        # QML functions in these upstream files have a four-space closing brace.
        start = text.index('function ' + name + '(')
        return text[start:text.index('\n    }', start) + 6]

    handlers = '\n'.join((qml_function(stream_qml, 'sessionFinished'),
                           qml_function(cli_qml, 'onLaunchFailed'),
                           qml_function(cli_qml, 'onAppQuitRequired')))
    js_setup = '''
var exits = [], errors = [], opened = 0, popped = 0, quitAfter = true;
var Qt = {exit: function(code) { exits.push(code); }, quit: function() { exits.push(0); }};
var console = {error: function(message) { errors.push(message); }};
var SdlGamepadKeyNavigation = {enable: function() {}};
var streamSegueErrorDialog = {text: "", open: function() { opened++; }};
var stackView = {pop: function() { popped++; }};
var window = {visible: false};
function qsTr(s) { return s; }
String.prototype.arg = function(s) { return this.replace("%1", s); };
'''
    native = r'''
#include <QCoreApplication>
#include <QJSEngine>
#include <QByteArray>
#include <SDL.h>
#include <cassert>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
extern "C" {
#include <libavcodec/avcodec.h>
#include "Limelight.h"
#include "h264_stream.h"
}
struct Backend { int caps; int getDecoderCapabilities() { return caps; } };
static bool needsSpsFixup(int format, const AVCodecHWConfig* hw, int caps) {
    struct { int videoFormat; } paramsValue{format};
    auto params = &paramsValue;
    auto m_HwDecodeCfg = hw;
    Backend backend{caps}; auto m_BackendRenderer = &backend;
    return SPS_CONDITION;
}
static bool quits(Uint8 pressed, int buttons) {
    SDL_ControllerButtonEvent eventValue{}; eventValue.state = pressed;
    auto event = &eventValue;
    struct { int buttons; } stateValue{buttons}; auto state = &stateValue;
    return QUIT_CONDITION;
}
#define MAX_SPS_EXTRA_SIZE 16
class FFmpegVideoDecoder {
public:
    bool m_NeedsSpsFixup;
    std::vector<uint8_t> m_DecodeBuffer;
    void writeBuffer(PLENTRY entry, int& offset);
};
WRITE_BUFFER
static void rewrite(const std::vector<uint8_t>& input, bool fixup, const char* path) {
    FFmpegVideoDecoder decoder{fixup, std::vector<uint8_t>(input.size() + 4096)};
    size_t pos = 0; int outputOffset = 0;
    while (pos < input.size()) {
        int start, end;
        find_nal_unit(const_cast<uint8_t*>(input.data() + pos), int(input.size() - pos), &start, &end);
        assert(end > start && size_t(end) <= input.size() - pos);
        LENTRY entry{};
        entry.data = reinterpret_cast<char*>(const_cast<uint8_t*>(input.data() + pos));
        entry.length = end;
        entry.bufferType = (input[pos + start] & 31) == 7 ? BUFFER_TYPE_SPS : BUFFER_TYPE_PICDATA;
        decoder.writeBuffer(&entry, outputOffset);
        pos += end;
    }
    if (!fixup) {
        assert(size_t(outputOffset) == input.size());
        assert(std::memcmp(input.data(), decoder.m_DecodeBuffer.data(), input.size()) == 0);
    }
    std::ofstream out(path, std::ios::binary);
    out.write(reinterpret_cast<char*>(decoder.m_DecodeBuffer.data()), outputOffset);
    assert(out.good());
}
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    AVCodecHWConfig drm{}; drm.device_type = AV_HWDEVICE_TYPE_DRM;
    AVCodecHWConfig vaapi{}; vaapi.device_type = AV_HWDEVICE_TYPE_VAAPI;
    assert(!needsSpsFixup(VIDEO_FORMAT_H264, &drm, 0));
    assert(needsSpsFixup(VIDEO_FORMAT_H264, nullptr, 0));
    assert(needsSpsFixup(VIDEO_FORMAT_H264, &vaapi, 0));
    assert(!needsSpsFixup(VIDEO_FORMAT_H265, &drm, 0));
    assert(!needsSpsFixup(VIDEO_FORMAT_H264, nullptr, CAPABILITY_REFERENCE_FRAME_INVALIDATION_AVC));
    qunsetenv("NO_GAMEPAD_QUIT");
    assert(!quits(SDL_PRESSED, LB_FLAG));
    assert(!quits(SDL_PRESSED, RB_FLAG));
    assert(!quits(SDL_PRESSED, A_FLAG));
    assert(quits(SDL_PRESSED, LB_FLAG | RB_FLAG));
    assert(quits(SDL_PRESSED, LB_FLAG | RB_FLAG | A_FLAG));
    assert(!quits(SDL_RELEASED, LB_FLAG | RB_FLAG));
    qputenv("NO_GAMEPAD_QUIT", "1");
    assert(!quits(SDL_PRESSED, LB_FLAG | RB_FLAG));
    QJSEngine engine;
    auto evaluate = [&](const char* code) {
        auto result = engine.evaluate(QString::fromUtf8(code));
        if (result.isError()) { std::cerr << result.toString().toStdString() << '\n'; std::abort(); }
        return result;
    };
    evaluate(JS_SETUP);
    evaluate(JS_HANDLERS);
    evaluate("onLaunchFailed('unreachable');");
    assert(evaluate("exits[0] === 1 && errors[0] === 'unreachable' && opened === 0").toBool());
    evaluate("exits=[]; onAppQuitRequired('Another game');");
    assert(evaluate("exits[0] === 1 && errors[1].indexOf('Another game') >= 0 && opened === 0").toBool());
    evaluate("exits=[]; sessionFinished(0);");
    assert(evaluate("exits.length === 1 && exits[0] === 0 && opened === 0").toBool());
    evaluate("exits=[]; streamSegueErrorDialog.text='Disconnected'; sessionFinished(-1);");
    assert(evaluate("exits.length === 1 && exits[0] === 1 && opened === 0").toBool());
    evaluate("exits=[]; quitAfter=false; sessionFinished(0);");
    assert(evaluate("exits.length === 0 && popped === 1 && window.visible && opened === 1").toBool());
    if (argc == 4) {
        std::ifstream in(argv[1], std::ios::binary);
        std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(in)), {});
        assert(!bytes.empty());
        rewrite(bytes, true, argv[2]);
        rewrite(bytes, needsSpsFixup(VIDEO_FORMAT_H264, &drm, 0), argv[3]);
    }
    std::cout << "QT_PATCH_CHECK PASS: SPS scope, original bytes, quit predicate, CLI/QML exits\n";
}
'''
    native = native.replace('SPS_CONDITION', sps_condition).replace('QUIT_CONDITION', quit_condition)
    native = native.replace('WRITE_BUFFER', write_buffer)
    native = native.replace('JS_SETUP', json.dumps(js_setup)).replace('JS_HANDLERS', json.dumps(handlers))
    cpp = output / 'qt-patch-check.cpp'
    cpp.write_text(native)
    h264 = source / 'h264bitstream/h264bitstream'
    objects = []
    for name in ('h264_nal', 'h264_sei', 'h264_stream'):
        obj = output / (name + '.o')
        run('cc', '-std=gnu99', '-w', '-c', str(h264 / (name + '.c')), '-o', str(obj))
        objects.append(str(obj))
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Qml', 'sdl2'], text=True))
    binary = output / 'qt-patch-check'
    run('g++', '-std=c++17', '-fPIC', '-I' + str(h264),
        '-I' + str(source / 'moonlight-common-c/moonlight-common-c/src'),
        '-I/usr/local/include', str(cpp), *objects, *flags, '-o', str(binary))
    command = [str(binary)]
    if args.fixture:
        command += [str(args.fixture.resolve()), str(output / 'sps-forced-one.h264'), str(output / 'sps-preserved.h264')]
    run(*command)


if __name__ == '__main__':
    main()
