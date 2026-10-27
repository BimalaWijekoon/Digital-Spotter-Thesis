"""Build frozen V5 candidate inputs from completed three-phase research reps.

Numerical construction is not live-scoring authorization. Training IMU units,
mounting axes and live pose equivalence still require separate validation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from digital_spotter.contracts import Quality, RepTransition
from digital_spotter.core.rep_phases import CompletedRep, PHASE_NAMES

from .v5_preprocessing import V5Preprocessor


VISION_COORDINATES = tuple(
    f"Vis_{joint}_{axis}"
    for joint in (
        "L_Shoulder", "R_Shoulder", "L_Hip", "R_Hip",
        "L_Knee", "R_Knee", "L_Ankle", "R_Ankle",
    )
    for axis in ("X", "Y")
)
IMU_FIELDS = (
    ("IMU_Acc_X", "acceleration_m_s2_x"),
    ("IMU_Acc_Y", "acceleration_m_s2_y"),
    ("IMU_Acc_Z", "acceleration_m_s2_z"),
    ("IMU_Gyro_X", "angular_velocity_rad_s_x"),
    ("IMU_Gyro_Y", "angular_velocity_rad_s_y"),
    ("IMU_Gyro_Z", "angular_velocity_rad_s_z"),
)
V5_TEMPORAL_FEATURES = (
    *VISION_COORDINATES,
    "Angle_Trunk_Inclination",
    "Hip_Flexion_Asymmetry",
    "Knee_Flexion_Asymmetry",
    "Ankle_Dorsiflexion_Asymmetry",
    "Knee_Hip_Coupling_L",
    "Knee_Hip_Coupling_R",
    *(target for target, _ in IMU_FIELDS),
    "IMU_Acc_Magnitude",
)


class V5FeatureUnavailable(ValueError):
    """A completed rep cannot supply a required, valid V5 candidate value."""


@dataclass(frozen=True)
class V5CandidateInputs:
    phases: tuple[Mapping[str, float | int], Mapping[str, float | int], Mapping[str, float | int]]
    context: Mapping[str, float | int]


def _required(source: Mapping[str, object], name: str, phase: int) -> float:
    value = source.get(name)
    if value is None or isinstance(value, (bool, str, bytes)):
        raise V5FeatureUnavailable(f"phase {phase} {name} unavailable")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise V5FeatureUnavailable(f"phase {phase} {name} unavailable") from exc
    if not math.isfinite(number):
        raise V5FeatureUnavailable(f"phase {phase} {name} unavailable")
    return number


def build_v5_candidate_inputs(
    rep: CompletedRep,
    *,
    exercise_id: int,
    load_kg: float,
    preprocessor: V5Preprocessor,
) -> V5CandidateInputs:
    """Use Stage 8 field order/formulas; never impute missing live measurements."""
    if tuple(preprocessor.temporal_features) != V5_TEMPORAL_FEATURES:
        raise ValueError("V5 feature registry mismatch")
    if tuple(preprocessor.context_features) != ("Exercise_ID", "Load_kg"):
        raise ValueError("V5 context registry mismatch")
    if exercise_id not in PHASE_NAMES or isinstance(exercise_id, bool):
        raise V5FeatureUnavailable("V5 exercise unavailable")
    if load_kg is None or isinstance(load_kg, (bool, str, bytes)):
        raise V5FeatureUnavailable("V5 load unavailable")
    try:
        load = float(load_kg)
    except (TypeError, ValueError, OverflowError) as exc:
        raise V5FeatureUnavailable("V5 load unavailable") from exc
    if not math.isfinite(load) or load < 0:
        raise V5FeatureUnavailable("V5 load unavailable")
    if rep.event.event is not RepTransition.COMPLETED or rep.event.quality is not Quality.GOOD:
        raise V5FeatureUnavailable("V5 rep quality unavailable")
    if len(rep.phases) != 3:
        raise V5FeatureUnavailable("V5 phase order unavailable")

    ordered: list[Mapping[str, float | int]] = []
    for number, phase in enumerate(rep.phases, 1):
        if phase.phase != number or phase.name != PHASE_NAMES[exercise_id][number - 1]:
            raise V5FeatureUnavailable("V5 phase order unavailable")
        if phase.quality is not Quality.GOOD or phase.frame_count < 1 or phase.imu is None:
            raise V5FeatureUnavailable(f"phase {number} IMU unavailable or degraded")

        vision = phase.vision
        values = {name: _required(vision, name, number) for name in VISION_COORDINATES}
        values["Angle_Trunk_Inclination"] = _required(vision, "Angle_Trunk_Inclination", number)
        hip_l = _required(vision, "Angle_Hip_Flexion_L", number)
        hip_r = _required(vision, "Angle_Hip_Flexion_R", number)
        knee_l = _required(vision, "Angle_Knee_Flexion_L", number)
        knee_r = _required(vision, "Angle_Knee_Flexion_R", number)
        ankle_l = _required(vision, "Angle_Ankle_Dorsiflexion_L", number)
        ankle_r = _required(vision, "Angle_Ankle_Dorsiflexion_R", number)
        values["Hip_Flexion_Asymmetry"] = abs(hip_l - hip_r)
        values["Knee_Flexion_Asymmetry"] = abs(knee_l - knee_r)
        values["Ankle_Dorsiflexion_Asymmetry"] = abs(ankle_l - ankle_r)
        values["Knee_Hip_Coupling_L"] = knee_l / (hip_l + 1e-6)
        values["Knee_Hip_Coupling_R"] = knee_r / (hip_r + 1e-6)
        for target, source in IMU_FIELDS:
            values[target] = _required(phase.imu, source, number)
        values["IMU_Acc_Magnitude"] = math.sqrt(sum(values[name] ** 2 for name, _ in IMU_FIELDS[:3]))
        if not all(math.isfinite(value) for value in values.values()):
            raise V5FeatureUnavailable(f"phase {number} engineered feature unavailable")
        ordered.append({"phase": number, **{name: values[name] for name in V5_TEMPORAL_FEATURES}})

    return V5CandidateInputs(tuple(ordered), {"Exercise_ID": exercise_id, "Load_kg": load})
