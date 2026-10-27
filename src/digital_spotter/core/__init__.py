"""Session, fusion, state-machine, and feedback domain logic."""

from digital_spotter.core.database_queue import (
    DatabaseQueueClosed,
    DatabaseQueueError,
    DatabaseQueueFull,
    DatabaseWorkQueue,
)
from digital_spotter.core.imu_ingest import IMUIngestCounters, UnixIMUEventServer
from digital_spotter.core.fusion import FusionEngine, FusionOutcome, FusionPolicy
from digital_spotter.core.rep_phases import CompletedRep, PhaseRecord, RepPhaseBuilder
from digital_spotter.core.vision_ingest import VisionIngestCounters, UnixVisionEventServer
from digital_spotter.core.sessions import (
    LocalSessionService,
    PoseCaptureStats,
    SessionError,
    SessionInputError,
    SessionRuntimeState,
    SessionStartRequest,
    SessionStateError,
    SessionView,
)
from digital_spotter.core.startup import StartupValidationError, require_model_package
from digital_spotter.core.replay import (
    ReplayAdapter,
    ReplayClock,
    ReplayFixture,
    ReplayFixtureError,
    ReplayResult,
    load_replay_fixture,
)

__all__ = [
    "DatabaseQueueClosed",
    "DatabaseQueueError",
    "DatabaseQueueFull",
    "DatabaseWorkQueue",
    "IMUIngestCounters",
    "FusionEngine",
    "FusionOutcome",
    "FusionPolicy",
    "CompletedRep",
    "PhaseRecord",
    "RepPhaseBuilder",
    "LocalSessionService",
    "PoseCaptureStats",
    "ReplayAdapter",
    "ReplayClock",
    "ReplayFixture",
    "ReplayFixtureError",
    "ReplayResult",
    "SessionError",
    "SessionInputError",
    "SessionRuntimeState",
    "SessionStartRequest",
    "SessionStateError",
    "SessionView",
    "VisionIngestCounters",
    "StartupValidationError",
    "load_replay_fixture",
    "require_model_package",
    "UnixIMUEventServer",
    "UnixVisionEventServer",
]
