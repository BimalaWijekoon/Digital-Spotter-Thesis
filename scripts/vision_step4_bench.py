#!/usr/bin/env python3
"""Bounded real-hardware gate for the M3-03 Picamera2/MediaPipe adapters."""

from __future__ import annotations

import argparse
import json
import site
import sys
import time
from dataclasses import asdict


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extra-site-packages")
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--restart-cycles", type=int, default=3)
    parser.add_argument("--camera-python", default="/usr/bin/python3")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not 1 <= args.frames <= 300:
        raise ValueError("frames must be between 1 and 300")
    if not 1 <= args.restart_cycles <= 5:
        raise ValueError("restart cycles must be between 1 and 5")
    if args.extra_site_packages:
        site.addsitedir(args.extra_site_packages)

    import cv2
    import mediapipe

    from digital_spotter.contracts import MonotonicNanoseconds, new_event_id
    from digital_spotter.vision import (
        MediaPipePoseAdapter,
        MediaPipePoseConfig,
        Picamera2FrameSource,
        Picamera2SourceConfig,
        VisionWorker,
        VisionWorkerConfig,
    )

    class Clock:
        def now_ns(self) -> MonotonicNanoseconds:
            return MonotonicNanoseconds(time.monotonic_ns())

    class Sink:
        def __init__(self) -> None:
            self.events = []

        def publish(self, event) -> None:
            self.events.append(event)

    source_config = Picamera2SourceConfig(
        python_executable=args.camera_python,
        main_size=(1280, 720),
        analysis_size=(640, 360),
        fps=30,
        encode_h264=True,
        max_consecutive_timeouts=3,
    )
    restarts = []
    restart_timestamps = []
    for _ in range(args.restart_cycles):
        source = Picamera2FrameSource(source_config)
        try:
            source.start()
            item = source.read(3.0)
            restarts.append(item is not None)
            if item is not None:
                restart_timestamps.append(item[0].timestamp.captured_monotonic_ns)
        finally:
            source.stop()

    sink = Sink()
    worker = VisionWorker(
        config=VisionWorkerConfig(
            camera_id="picamera2-imx219",
            device_id="pidigitalspotter",
            minimum_confidence=0.7,
            read_timeout_s=2.0,
        ),
        source=Picamera2FrameSource(source_config),
        evaluator=MediaPipePoseAdapter(MediaPipePoseConfig(model_complexity=1)),
        sink=sink,
        clock=Clock(),
        event_id_factory=new_event_id,
    )
    started_ns = time.monotonic_ns()
    summary = worker.run(max_frames=args.frames)
    elapsed_s = (time.monotonic_ns() - started_ns) / 1_000_000_000.0
    captures = [int(event.payload.captured_monotonic_ns) for event in sink.events]
    result = {
        "evidence_environment": "E3_pi_hardware_bench",
        "hardware_simulated": False,
        "camera": "imx219",
        "opencv_version": cv2.__version__,
        "mediapipe_version": mediapipe.__version__,
        "restart_results": restarts,
        "restart_capture_timestamps": restart_timestamps,
        "restart_passed": all(restarts),
        "worker": asdict(summary),
        "elapsed_s": round(elapsed_s, 3),
        "worker_wall_effective_fps_including_startup": round(
            len(sink.events) / elapsed_s,
            3,
        ),
        "capture_timestamps_strictly_monotonic": all(
            current > previous for previous, current in zip(captures, captures[1:])
        ),
        "quality_counts": {
            quality: sum(event.quality.value == quality for event in sink.events)
            for quality in sorted({event.quality.value for event in sink.events})
        },
        "landmark_count_min": min(
            (len(event.payload.landmarks) for event in sink.events),
            default=0,
        ),
        "landmark_count_max": max(
            (len(event.payload.landmarks) for event in sink.events),
            default=0,
        ),
    }
    print(json.dumps(result, indent=2, sort_keys=True, default=lambda value: value.value))
    return 0 if all(restarts) and summary.events_published == args.frames else 2


if __name__ == "__main__":
    raise SystemExit(main())
