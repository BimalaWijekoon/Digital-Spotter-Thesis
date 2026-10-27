#!/usr/bin/env python3
"""Publish real Pi camera H.264 only while MediaMTX has a research viewer."""

import argparse
import json
import signal
import site


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish-url", required=True)
    parser.add_argument("--extra-site-packages", required=True)
    args = parser.parse_args()
    site.addsitedir(args.extra_site_packages)

    from digital_spotter.vision.adapters import Picamera2FrameSource, Picamera2SourceConfig
    from digital_spotter.vision.errors import CameraUnavailableError

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
        print("RESEARCH_CAMERA_STARTED: real Picamera2, H264, no recording, no pose inference", flush=True)
        while running:
            try:
                if source.read(3.0) is not None:
                    frames += 1
            except CameraUnavailableError:
                if running:
                    raise
                break
    finally:
        source.stop()
    print(json.dumps({"frames_received": frames, "hardware_simulated": False,
                      "raw_video_saved": False, "clean_stop": True}), flush=True)
    return 0 if frames else 1


if __name__ == "__main__":
    raise SystemExit(main())
