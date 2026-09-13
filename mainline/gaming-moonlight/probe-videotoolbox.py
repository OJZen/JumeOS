#!/usr/bin/env python3
"""Bounded synthetic H.264 A/B; no screen capture, network or services."""

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess


def summarize(framecrc):
    pts = []
    for line in framecrc.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split(",")
        if len(fields) < 6:
            raise ValueError("Incomplete framecrc packet row")
        pts.append(int(fields[2]))
    return {
        "packets": len(pts),
        "first_pts": pts[0] if pts else None,
        "last_pts": pts[-1] if pts else None,
        "pts_step_counts": dict(Counter(b - a for a, b in zip(pts, pts[1:]))),
    }


def self_test():
    result = summarize("# header\n0, 0, 1, 1, 10, 0x1\n0, 2, 3, 1, 11, 0x2\n")
    assert result == {"packets": 2, "first_pts": 1, "last_pts": 3, "pts_step_counts": {2: 1}}
    assert summarize("# no packets\n")["packets"] == 0
    try:
        summarize("0, 1, 2")
    except ValueError:
        pass
    else:
        raise AssertionError("Malformed packet accepted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?", help="new evidence directory on external workspace")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("VIDEOTOOLBOX_PROBE_PARSER PASS")
        return
    if args.output is None:
        parser.error("output is required")
    args.output.mkdir(parents=True, exist_ok=False)
    version = subprocess.check_output([args.ffmpeg, "-version"], text=True, timeout=10)
    (args.output / "ffmpeg-version.txt").write_text(version)
    results = []
    for refs in (1, 0):
        command = [
            args.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "warning",
            "-f", "lavfi", "-i", "testsrc2=size=640x480:rate=60",
            "-frames:v", "120", "-an", "-c:v", "h264_videotoolbox",
            "-pix_fmt", "nv12", "-realtime", "1", "-max_ref_frames", str(refs),
            "-bf", "0", "-g", "2147483647", "-b:v", "2708k",
            "-profile:v", "high", "-flags", "+low_delay", "-f", "framecrc", "-",
        ]
        run = subprocess.run(command, capture_output=True, text=True, timeout=30)
        (args.output / f"ref{refs}.framecrc").write_text(run.stdout)
        (args.output / f"ref{refs}.log").write_text(run.stderr)
        results.append({"refs": refs, "returncode": run.returncode, "command": command, **summarize(run.stdout)})
        (args.output / "result.json").write_text(json.dumps(results, indent=2) + "\n")
        if run.returncode:
            raise SystemExit(f"Encoder failed; inspect ref{refs}.log (not a frame-rate result)")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
