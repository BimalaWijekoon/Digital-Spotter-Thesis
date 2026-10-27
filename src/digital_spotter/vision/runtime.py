"""Feature-gated standalone runtime for the canonical vision worker."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from pydantic import ValidationError

from digital_spotter.config import (
    AdapterMode,
    ProductSettings,
    RuntimeProfile,
    SettingsLoadError,
    VisionPipeline,
    load_settings,
)
from digital_spotter.contracts import MonotonicNanoseconds, new_event_id
from digital_spotter.vision.adapters import (
    MediaPipePoseAdapter,
    MediaPipePoseConfig,
    Picamera2FrameSource,
    Picamera2SourceConfig,
)
from digital_spotter.vision.errors import VisionAdapterError
from digital_spotter.vision.uds import (
    BoundedVisionEventPublisher,
    UnixVisionEventTransport,
)
from digital_spotter.vision.worker import VisionWorker, VisionWorkerConfig


LOGGER = logging.getLogger("digital_spotter.vision")
VISION_EVENT_SOCKET_NAME = "vision-events.sock"


class _Worker(Protocol):
    def run(self): ...
    def stop(self) -> None: ...


class _Publisher(Protocol):
    def start(self) -> None: ...
    def close(self, *, timeout_s: float = 1.0) -> None: ...


class _SystemMonotonicClock:
    def now_ns(self) -> MonotonicNanoseconds:
        return MonotonicNanoseconds(time.monotonic_ns())


@dataclass(frozen=True)
class RealVisionRuntimeConfig:
    camera_id: str
    camera_python: str
    socket_path: Path
    allowed_peer_uids: frozenset[int] | None = None
    publish_url: str | None = None
    queue_size: int = 4
    close_timeout_s: float = 2.0

    def __post_init__(self) -> None:
        if not self.camera_python:
            raise ValueError("camera Python executable must not be empty")
        if self.queue_size < 1 or self.queue_size > 16:
            raise ValueError("vision queue size must be between 1 and 16")
        if not 0.1 <= self.close_timeout_s <= 10.0:
            raise ValueError("vision close timeout must be between 0.1 and 10 seconds")


class VisionAgentRuntime:
    """Own one worker and publisher for one process lifetime."""

    def __init__(
        self,
        *,
        worker: _Worker,
        publisher: _Publisher,
        close_timeout_s: float = 2.0,
    ) -> None:
        if not 0.1 <= close_timeout_s <= 10.0:
            raise ValueError("vision close timeout must be between 0.1 and 10 seconds")
        self.worker = worker
        self.publisher = publisher
        self.close_timeout_s = close_timeout_s
        self._started = False

    def run(self):
        if self._started:
            raise RuntimeError("vision runtime instances can run only once")
        self._started = True
        self.publisher.start()
        try:
            summary = self.worker.run()
        except BaseException:
            try:
                self.publisher.close(timeout_s=self.close_timeout_s)
            except Exception:
                LOGGER.exception("vision publisher cleanup failed after worker failure")
            raise
        self.publisher.close(timeout_s=self.close_timeout_s)
        return summary

    def stop(self) -> None:
        self.worker.stop()


def build_real_vision_runtime(
    *,
    settings: ProductSettings,
    config: RealVisionRuntimeConfig,
) -> VisionAgentRuntime:
    """Assemble only the real canonical adapters after the feature gate passes."""

    if settings.vision_pipeline is not VisionPipeline.CANONICAL:
        raise ValueError("canonical vision runtime is disabled by vision_pipeline")
    if settings.vision_adapter is not AdapterMode.REAL:
        raise ValueError("canonical vision runtime requires vision_adapter=real")

    publisher = BoundedVisionEventPublisher(
        transport=UnixVisionEventTransport(
            config.socket_path,
            allowed_peer_uids=config.allowed_peer_uids,
        ),
        queue_size=config.queue_size,
    )
    worker = VisionWorker(
        config=VisionWorkerConfig(
            camera_id=config.camera_id,
            device_id=settings.device_id,
        ),
        source=Picamera2FrameSource(
            Picamera2SourceConfig(
                python_executable=config.camera_python,
                publish_url=config.publish_url,
            )
        ),
        evaluator=MediaPipePoseAdapter(MediaPipePoseConfig()),
        sink=publisher,
        health_sink=publisher,
        clock=_SystemMonotonicClock(),
        event_id_factory=new_event_id,
    )
    return VisionAgentRuntime(
        worker=worker,
        publisher=publisher,
        close_timeout_s=config.close_timeout_s,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ds-vision-agent")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--camera-python", required=True)
    parser.add_argument("--socket", type=Path)
    parser.add_argument("--core-uid", type=int, action="append", default=[])
    parser.add_argument("--publish-url")
    parser.add_argument("--queue-size", type=int, default=4)
    parser.add_argument("--close-timeout", type=float, default=2.0)
    return parser


def _install_signal_handlers(runtime: VisionAgentRuntime) -> None:
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda _signum, _frame: runtime.stop())


def _safe_summary(summary) -> dict[str, object]:
    return {
        "state": summary.state.value,
        "adapter_mode": summary.adapter_mode,
        "pose_evaluator_mode": summary.pose_evaluator_mode,
        "is_simulated": summary.is_simulated,
        "frames_received": summary.frames_received,
        "events_published": summary.events_published,
        "source_frames_dropped": summary.source_frames_dropped,
        "poses_not_found": summary.poses_not_found,
        "poses_low_visibility": summary.poses_low_visibility,
        "read_timeouts": summary.read_timeouts,
        "processing_failures": summary.processing_failures,
        "health_events_published": summary.health_events_published,
        "health_publish_failures": summary.health_publish_failures,
        "last_failure_reason": (
            summary.last_failure_reason.value
            if summary.last_failure_reason is not None
            else None
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        settings = load_settings(args.config)
        if settings.vision_pipeline is not VisionPipeline.CANONICAL:
            print(
                "canonical vision agent disabled; legacy migration path remains active",
                file=sys.stderr,
            )
            return 3
        if settings.vision_adapter is not AdapterMode.REAL:
            print(
                "canonical vision agent requires DS_VISION_ADAPTER=real",
                file=sys.stderr,
            )
            return 3
        if settings.profile is RuntimeProfile.PRODUCTION and not args.core_uid:
            raise ValueError("production vision runtime requires at least one core peer UID")
        socket_path = args.socket or settings.runtime_dir / VISION_EVENT_SOCKET_NAME
        if settings.profile is RuntimeProfile.PRODUCTION and not socket_path.is_absolute():
            raise ValueError("production vision socket path must be absolute")
        runtime = build_real_vision_runtime(
            settings=settings,
            config=RealVisionRuntimeConfig(
                camera_id=args.camera_id,
                camera_python=args.camera_python,
                socket_path=socket_path,
                allowed_peer_uids=(
                    frozenset(args.core_uid) if args.core_uid else None
                ),
                publish_url=args.publish_url or settings.video_publish_url,
                queue_size=args.queue_size,
                close_timeout_s=args.close_timeout,
            ),
        )
        _install_signal_handlers(runtime)
        summary = runtime.run()
    except (OSError, SettingsLoadError, ValidationError, ValueError, VisionAdapterError) as exc:
        print(f"vision agent startup/runtime failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(_safe_summary(summary), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
