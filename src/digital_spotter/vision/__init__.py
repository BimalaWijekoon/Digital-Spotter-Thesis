"""Camera, pose, and video worker adapters."""

from digital_spotter.vision.adapters import (
    LocalPicamera2HelperLauncher,
    MediaPipePoseAdapter,
    MediaPipePoseConfig,
    Picamera2FrameSource,
    Picamera2SourceConfig,
)
from digital_spotter.vision.errors import (
    CameraProtocolError,
    CameraUnavailableError,
    PoseProcessingError,
    PoseUnavailableError,
    VisionAdapterError,
)
from digital_spotter.vision.frames import (
    CameraFrame,
    CameraFrameError,
    CaptureTimestamp,
    CaptureTimestampSource,
    LatestFrameSlot,
    picamera2_capture_timestamp,
)
from digital_spotter.vision.health import (
    VISION_COMPONENT,
    VISION_HEALTH_VERSION,
    VisionHealthSnapshot,
    VisionWatchdog,
    build_vision_health_envelope,
)
from digital_spotter.vision.pose_events import (
    PoseBuildResult,
    PoseEvaluation,
    PoseEventError,
    build_pose_envelope,
    build_pose_sample,
)
from digital_spotter.vision.replay import (
    ReplayFrameSource,
    ReplayPoseEvaluator,
    VisionReplayError,
)
from digital_spotter.vision.worker import (
    VisionWorker,
    VisionWorkerConfig,
    VisionWorkerState,
    VisionWorkerSummary,
)
from digital_spotter.vision.uds import (
    BoundedVisionEventPublisher,
    UnixVisionEventTransport,
    VisionPublisherCounters,
    VisionUDSError,
)

__all__ = [
    "CameraFrame",
    "CameraFrameError",
    "CameraProtocolError",
    "CameraUnavailableError",
    "CaptureTimestamp",
    "CaptureTimestampSource",
    "LatestFrameSlot",
    "LocalPicamera2HelperLauncher",
    "MediaPipePoseAdapter",
    "MediaPipePoseConfig",
    "Picamera2FrameSource",
    "Picamera2SourceConfig",
    "PoseBuildResult",
    "PoseEvaluation",
    "PoseEventError",
    "PoseProcessingError",
    "PoseUnavailableError",
    "ReplayFrameSource",
    "ReplayPoseEvaluator",
    "UnixVisionEventTransport",
    "VISION_COMPONENT",
    "VISION_HEALTH_VERSION",
    "VisionHealthSnapshot",
    "VisionPublisherCounters",
    "VisionReplayError",
    "VisionUDSError",
    "VisionAdapterError",
    "VisionWatchdog",
    "VisionWorker",
    "VisionWorkerConfig",
    "VisionWorkerState",
    "VisionWorkerSummary",
    "BoundedVisionEventPublisher",
    "build_pose_envelope",
    "build_pose_sample",
    "build_vision_health_envelope",
    "picamera2_capture_timestamp",
]
