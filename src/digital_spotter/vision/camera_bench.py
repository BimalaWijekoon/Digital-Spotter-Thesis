"""Bounded real-hardware runner for the R13-C camera-owner spike.

Heavy camera and pose dependencies are imported only when a real candidate is
selected. Deterministic unit tests can therefore exercise the lifecycle and
measurement logic without pretending to be real hardware evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import socket
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from digital_spotter.vision.adapters import (
    MediaPipePoseAdapter,
    MediaPipePoseConfig,
    Picamera2FrameSource,
    Picamera2SourceConfig,
    _receive_exact as _adapter_receive_exact,
)
from digital_spotter.vision.camera_spike import (
    CameraFrame,
    CameraSpikeError,
    CaptureTimestamp,
    CaptureTimestampSource,
    FrameMeasurement,
    LatestFrameSlot,
    PoseMeasurement,
    picamera2_capture_timestamp,
    summarize_measurements,
)
from digital_spotter.vision.errors import VisionAdapterError


class FrameSource(Protocol):
    def start(self) -> None: ...
    def read(self, timeout_s: float) -> tuple[CameraFrame, int] | None: ...
    def stop(self) -> None: ...


class PoseEvaluator(Protocol):
    def process(self, pixels: object) -> PoseMeasurement: ...
    def close(self) -> None: ...


class RTSPFrameSource:
    """MediaMTX-owned camera candidate with latest-frame RTSP decode."""

    def __init__(self, url: str, *, analysis_size: tuple[int, int]) -> None:
        self.url = url
        self.analysis_size = analysis_size
        self._capture = None
        self._cv2 = None
        self._slot: LatestFrameSlot[CameraFrame] | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._consumer_generation = 0
        self._sequence = 0

    def start(self) -> None:
        if self._running:
            raise CameraSpikeError("RTSP source is already running")
        os.environ.setdefault(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS",
            "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay",
        )
        try:
            import cv2
        except ImportError as exc:
            raise CameraSpikeError("OpenCV is unavailable for RTSP decode") from exc
        capture = cv2.VideoCapture(self.url)
        if not capture.isOpened():
            capture.release()
            raise CameraSpikeError(f"RTSP camera unavailable: {self.url}")
        self._capture = capture
        self._cv2 = cv2
        self._slot = LatestFrameSlot()
        self._consumer_generation = 0
        self._sequence = 0
        self._running = True
        self._thread = threading.Thread(
            target=self._drain,
            daemon=True,
            name="R13C-RTSP-latest-frame",
        )
        self._thread.start()

    def _drain(self) -> None:
        assert self._capture is not None
        assert self._cv2 is not None
        assert self._slot is not None
        while self._running:
            ok, pixels = self._capture.read()
            received_ns = time.monotonic_ns()
            if not ok or pixels is None:
                time.sleep(0.02)
                continue
            target_width, target_height = self.analysis_size
            if pixels.shape[1] != target_width or pixels.shape[0] != target_height:
                pixels = self._cv2.resize(
                    pixels,
                    (target_width, target_height),
                    interpolation=self._cv2.INTER_AREA,
                )
            self._sequence += 1
            height, width = pixels.shape[:2]
            try:
                self._slot.publish(
                    CameraFrame(
                        sequence=self._sequence,
                        received_monotonic_ns=received_ns,
                        width=width,
                        height=height,
                        timestamp=CaptureTimestamp(
                            captured_monotonic_ns=None,
                            source=CaptureTimestampSource.ARRIVAL_ONLY,
                        ),
                        pixels=pixels,
                    )
                )
            except RuntimeError:
                return

    def read(self, timeout_s: float) -> tuple[CameraFrame, int] | None:
        if not self._running or self._slot is None:
            raise CameraSpikeError("RTSP source is not running")
        item = self._slot.wait_after(
            self._consumer_generation,
            timeout_s=timeout_s,
        )
        if item is None:
            return None
        generation, frame, dropped = item
        self._consumer_generation = generation
        return frame, dropped

    def stop(self) -> None:
        self._running = False
        if self._slot is not None:
            self._slot.close()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        if self._capture is not None:
            self._capture.release()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        self._capture = None
        self._cv2 = None
        self._slot = None


def _receive_exact(connection: socket.socket, size: int) -> bytes:
    """Retain the measurement-spike exception contract around canonical framing."""

    try:
        return _adapter_receive_exact(connection, size)
    except VisionAdapterError as exc:
        raise CameraSpikeError(str(exc)) from exc


class Picamera2ProcessSource(Picamera2FrameSource):
    """Compatibility constructor for the R13-C benchmark command."""

    def __init__(
        self,
        *,
        python_executable: str,
        main_size: tuple[int, int],
        analysis_size: tuple[int, int],
        fps: int,
        encode_h264: bool,
        publish_url: str | None = None,
    ) -> None:
        super().__init__(
            Picamera2SourceConfig(
                python_executable=python_executable,
                main_size=main_size,
                analysis_size=analysis_size,
                fps=fps,
                encode_h264=encode_h264,
                publish_url=publish_url,
            )
        )


class MediaPipePoseEvaluator:
    """R13-C metric wrapper around the canonical real MediaPipe adapter."""

    def __init__(self, *, model_complexity: int, visibility_threshold: float) -> None:
        self._adapter = MediaPipePoseAdapter(
            MediaPipePoseConfig(model_complexity=model_complexity)
        )
        self._visibility_threshold = visibility_threshold

    def process(self, pixels: object) -> PoseMeasurement:
        started_ns = time.monotonic_ns()
        result = self._adapter.evaluate_pixels(pixels)
        finished_ns = time.monotonic_ns()
        return PoseMeasurement(
            found=result.found,
            valid=result.found and result.confidence >= self._visibility_threshold,
            confidence=result.confidence,
            processing_time_ns=finished_ns - started_ns,
        )

    def close(self) -> None:
        self._adapter.close()


@dataclass(frozen=True)
class ResourceSummary:
    process_cpu_pct: float
    rss_start_mb: float
    rss_end_mb: float
    rss_peak_mb: float
    stack_cpu_pct: float
    stack_rss_start_mb: float
    stack_rss_end_mb: float
    stack_rss_peak_mb: float
    stack_processes: tuple[str, ...]
    temperature_start_c: float | None
    temperature_end_c: float | None
    temperature_peak_c: float | None
    throttled_start: str
    throttled_end: str


def _rss_mb() -> float:
    with Path("/proc/self/statm").open(encoding="ascii") as handle:
        resident_pages = int(handle.read().split()[1])
    return resident_pages * os.sysconf("SC_PAGE_SIZE") / (1024.0 * 1024.0)


def _process_ticks(pid: int) -> int | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        fields = raw[raw.rfind(")") + 2 :].split()
        return int(fields[11]) + int(fields[12])
    except (OSError, ValueError, IndexError):
        return None


def _process_rss_mb(pid: int) -> float | None:
    try:
        with Path(f"/proc/{pid}/statm").open(encoding="ascii") as handle:
            resident_pages = int(handle.read().split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return resident_pages * os.sysconf("SC_PAGE_SIZE") / (1024.0 * 1024.0)


def _stack_processes(candidate: str) -> dict[int, str]:
    """Find only the processes that belong to the active camera candidate."""

    selected = {os.getpid(): "pose-benchmark"}
    for process_path in Path("/proc").iterdir():
        if not process_path.name.isdigit():
            continue
        pid = int(process_path.name)
        if pid in selected:
            continue
        try:
            command = (process_path / "cmdline").read_bytes().replace(b"\x00", b" ").decode(
                errors="replace"
            )
            name = (process_path / "comm").read_text(encoding="ascii").strip()
        except OSError:
            continue
        if candidate == "picamera2":
            if (
                "digital_spotter.vision.picamera2_helper" in command
                or "picamera2_helper.py" in command
            ):
                selected[pid] = "picamera2-helper"
            elif name == "mediamtx":
                selected[pid] = "mediamtx-relay"
        elif candidate == "mediamtx-rtsp" and name in {"mediamtx", "mtxrpicam"}:
            selected[pid] = name
    return selected


def _stack_snapshot(processes: dict[int, str]) -> tuple[dict[int, int], float]:
    ticks: dict[int, int] = {}
    total_rss_mb = 0.0
    for pid in processes:
        process_ticks = _process_ticks(pid)
        process_rss = _process_rss_mb(pid)
        if process_ticks is not None:
            ticks[pid] = process_ticks
        if process_rss is not None:
            total_rss_mb += process_rss
    return ticks, total_rss_mb


def _temperature_c() -> float | None:
    try:
        raw = Path("/sys/class/thermal/thermal_zone0/temp").read_text(encoding="ascii")
        return int(raw.strip()) / 1000.0
    except (OSError, ValueError):
        return None


def _throttled() -> str:
    try:
        return subprocess.check_output(
            ["vcgencmd", "get_throttled"],
            text=True,
            timeout=2.0,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def run_restart_probe(source_factory, *, cycles: int) -> tuple[bool, ...]:
    results: list[bool] = []
    for _ in range(cycles):
        source = source_factory()
        try:
            source.start()
            results.append(source.read(3.0) is not None)
        except (CameraSpikeError, VisionAdapterError):
            results.append(False)
        finally:
            source.stop()
    return tuple(results)


def run_benchmark(
    *,
    candidate: str,
    source: FrameSource,
    evaluator: PoseEvaluator,
    duration_s: float,
    person_required: bool,
) -> tuple[object, ResourceSummary]:
    measurements: list[FrameMeasurement] = []
    temperatures: list[float] = []
    rss_start = _rss_mb()
    temperature_start = _temperature_c()
    if temperature_start is not None:
        temperatures.append(temperature_start)
    throttled_start = _throttled()
    cpu_start = time.process_time()
    wall_start = time.monotonic()
    source_started = False
    stack_processes: dict[int, str] = {}
    stack_ticks_start: dict[int, int] = {}
    stack_ticks_end: dict[int, int] = {}
    stack_rss_start = 0.0
    stack_rss_end = 0.0
    stack_rss_peak = 0.0
    stack_wall_start = 0.0
    stack_wall_s = 0.0
    try:
        source.start()
        source_started = True
        stack_processes = _stack_processes(candidate)
        stack_ticks_start, stack_rss_start = _stack_snapshot(stack_processes)
        stack_rss_peak = stack_rss_start
        stack_wall_start = time.monotonic()
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            item = source.read(3.0)
            if item is None:
                continue
            frame, dropped = item
            pose = evaluator.process(frame.pixels)
            processed_ns = time.monotonic_ns()
            measurements.append(
                FrameMeasurement(
                    frame_sequence=frame.sequence,
                    captured_monotonic_ns=frame.timestamp.captured_monotonic_ns,
                    received_monotonic_ns=frame.received_monotonic_ns,
                    processed_monotonic_ns=processed_ns,
                    timestamp_source=frame.timestamp.source,
                    width=frame.width,
                    height=frame.height,
                    dropped_since_previous=dropped,
                    pose_found=pose.found,
                    pose_valid=pose.valid,
                    pose_confidence=pose.confidence,
                    pose_processing_time_ns=pose.processing_time_ns,
                )
            )
            temperature = _temperature_c()
            if temperature is not None:
                temperatures.append(temperature)
            _, stack_rss_current = _stack_snapshot(stack_processes)
            stack_rss_peak = max(stack_rss_peak, stack_rss_current)
    finally:
        try:
            if source_started:
                stack_ticks_end, stack_rss_end = _stack_snapshot(stack_processes)
                stack_wall_s = max(time.monotonic() - stack_wall_start, 0.000001)
                stack_rss_peak = max(stack_rss_peak, stack_rss_end)
                source.stop()
        finally:
            evaluator.close()
    wall_s = max(time.monotonic() - wall_start, 0.000001)
    process_cpu_pct = 100.0 * (time.process_time() - cpu_start) / wall_s
    stack_tick_delta = sum(
        max(0, stack_ticks_end[pid] - started)
        for pid, started in stack_ticks_start.items()
        if pid in stack_ticks_end
    )
    stack_cpu_pct = (
        100.0 * stack_tick_delta / (stack_wall_s * os.sysconf("SC_CLK_TCK"))
        if stack_wall_s > 0
        else 0.0
    )
    rss_end = _rss_mb()
    rss_peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    temperature_end = _temperature_c()
    if temperature_end is not None:
        temperatures.append(temperature_end)
    resources = ResourceSummary(
        process_cpu_pct=round(process_cpu_pct, 1),
        rss_start_mb=round(rss_start, 1),
        rss_end_mb=round(rss_end, 1),
        rss_peak_mb=round(max(rss_peak, rss_start, rss_end), 1),
        stack_cpu_pct=round(stack_cpu_pct, 1),
        stack_rss_start_mb=round(stack_rss_start, 1),
        stack_rss_end_mb=round(stack_rss_end, 1),
        stack_rss_peak_mb=round(max(stack_rss_peak, stack_rss_start, stack_rss_end), 1),
        stack_processes=tuple(stack_processes.values()),
        temperature_start_c=temperature_start,
        temperature_end_c=temperature_end,
        temperature_peak_c=max(temperatures) if temperatures else None,
        throttled_start=throttled_start,
        throttled_end=_throttled(),
    )
    summary = summarize_measurements(
        candidate,
        measurements,
        person_required=person_required,
        capture_timestamps_required=True,
    )
    return summary, resources


def _validate_args(args: argparse.Namespace) -> None:
    if not 5.0 <= args.duration <= 120.0:
        raise ValueError("duration must be between 5 and 120 seconds")
    if not 0 <= args.restart_cycles <= 5:
        raise ValueError("restart cycles must be between zero and five")
    if args.fps not in (15, 30):
        raise ValueError("camera FPS must be 15 or 30")
    if args.model_complexity not in (0, 1, 2):
        raise ValueError("MediaPipe model complexity must be 0, 1, or 2")


def _source_factory(args: argparse.Namespace):
    if args.candidate == "picamera2":
        return lambda: Picamera2ProcessSource(
            python_executable=args.picamera_python,
            main_size=(args.main_width, args.main_height),
            analysis_size=(args.analysis_width, args.analysis_height),
            fps=args.fps,
            encode_h264=args.encode_h264,
            publish_url=args.publish_url,
        )
    return lambda: RTSPFrameSource(
        args.rtsp_url,
        analysis_size=(args.analysis_width, args.analysis_height),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", choices=("picamera2", "mediamtx-rtsp"), required=True)
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--restart-cycles", type=int, default=3)
    parser.add_argument("--main-width", type=int, default=1280)
    parser.add_argument("--main-height", type=int, default=720)
    parser.add_argument("--analysis-width", type=int, default=640)
    parser.add_argument("--analysis-height", type=int, default=360)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--model-complexity", type=int, default=1)
    parser.add_argument("--visibility-threshold", type=float, default=0.15)
    parser.add_argument("--rtsp-url", default="rtsp://127.0.0.1:8554/picam")
    parser.add_argument("--picamera-python", default="/usr/bin/python3")
    parser.add_argument("--encode-h264", action="store_true")
    parser.add_argument("--publish-url")
    parser.add_argument("--person-required", action="store_true")
    args = parser.parse_args(argv)
    try:
        _validate_args(args)
        factory = _source_factory(args)
        restart_results = run_restart_probe(factory, cycles=args.restart_cycles)
        source = factory()
        evaluator = MediaPipePoseEvaluator(
            model_complexity=args.model_complexity,
            visibility_threshold=args.visibility_threshold,
        )
        summary, resources = run_benchmark(
            candidate=args.candidate,
            source=source,
            evaluator=evaluator,
            duration_s=args.duration,
            person_required=args.person_required,
        )
    except (CameraSpikeError, VisionAdapterError, ValueError) as exc:
        print(json.dumps({"candidate": args.candidate, "error": str(exc)}))
        return 2
    output = {
        "evidence_environment": "real_hardware",
        "hardware_simulated": False,
        "candidate": args.candidate,
        "restart_results": restart_results,
        "restart_passed": all(restart_results),
        "measurement": asdict(summary),
        "resources": asdict(resources),
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if all(restart_results) and not summary.failed_checks else 2


if __name__ == "__main__":
    raise SystemExit(main())
