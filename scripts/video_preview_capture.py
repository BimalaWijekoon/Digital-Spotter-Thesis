#!/usr/bin/env python3
"""Bounded empty-scene publication using the existing camera adapter; no recording."""

import argparse
import json
import signal
import site
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish-url", required=True)
    parser.add_argument("--duration", type=int, default=120)
    parser.add_argument("--extra-site-packages")
    args = parser.parse_args()
    if not 10 <= args.duration <= 300:
        parser.error("duration must be 10..300 seconds")
    # Extend this diagnostic interpreter only. PYTHONPATH would leak Python 3.12
    # binary wheels into the separate system-Python Picamera2 helper.
    if args.extra_site_packages:
        site.addsitedir(args.extra_site_packages)
    from digital_spotter.vision.adapters import Picamera2FrameSource, Picamera2SourceConfig

    running = True

    def stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    source = Picamera2FrameSource(Picamera2SourceConfig(publish_url=args.publish_url))
    frames = 0
    try:
        source.start()
        started = time.monotonic()
        print("PREVIEW_STARTED: real Picamera2, H264, no recording, no pose inference", flush=True)
        while running and time.monotonic() - started < args.duration:
            if source.read(3.0) is not None:
                frames += 1
    finally:
        source.stop()
    print(json.dumps({"frames_received": frames, "hardware_simulated": False,
                      "raw_video_saved": False, "clean_stop": True}))
    return 0 if frames else 1


if __name__ == "__main__":
    raise SystemExit(main())
