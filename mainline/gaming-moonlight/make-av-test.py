#!/usr/bin/env python3
"""Create a quiet deterministic local/streaming reference; never starts playback."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import wave

repo = Path(__file__).resolve().parents[2]


def build(output):
    output = output.resolve()
    if not output.is_relative_to(repo / "mainline/out") or output.exists():
        raise ValueError("use a new output directory under mainline/out")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError("ffmpeg is required for the video reference")
    output.mkdir(parents=True, mode=0o700)
    rate, duration, amplitude = 48000, 12, 0.03
    samples = bytearray()
    for frame in range(rate * duration):
        t = frame / rate
        phase = (t - 1) % 2
        envelope = max(0.0, min(1.0, phase / .005, (.1 - phase) / .005)) if t >= 1 and phase < .1 else 0
        sample = round(32767 * amplitude * envelope * math.sin(2 * math.pi * 1000 * t))
        samples.extend(struct.pack("<hh", sample, sample))
    sound = output / "reference.wav"
    with wave.open(str(sound), "wb") as stream:
        stream.setnchannels(2); stream.setsampwidth(2); stream.setframerate(rate); stream.writeframes(samples)
    assert len(samples) == rate * duration * 4
    assert max(abs(value[0]) for value in struct.iter_unpack("<h", samples)) <= 984
    video = output / "reference.mkv"
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=c=0x101010:s=640x480:r=60:d=12",
                    "-i", str(sound), "-vf", "drawbox=x=270:y=190:w=100:h=100:color=white:t=fill:enable='gte(t,1)*lt(mod(t-1,2),0.1)'",
                    "-map", "0:v", "-map", "1:a", "-c:v", "ffv1", "-level", "3", "-c:a", "pcm_s16le", "-shortest", str(video)], check=True)
    record = {"rate": rate, "channels": 2, "duration_seconds": duration, "peak_fraction": amplitude,
              "tone_hz": 1000, "fade_ms": 5, "cue_seconds": [1, 3, 5, 7, 9, 11],
              "files": {p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in (sound, video)},
              "use": "Same audio locally and through Sunshine; compare at the accepted mixer level. No playback or audible acceptance was performed."}
    (output / "receipt.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)
