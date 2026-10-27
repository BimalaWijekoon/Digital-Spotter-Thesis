"""Deterministic completed-rep to frozen-V5 candidate-input checks (no live scoring)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from digital_spotter.contracts import Quality, RepEvent, RepTransition
from digital_spotter.core.rep_phases import CompletedRep, PHASE_NAMES, PhaseRecord
from digital_spotter.inference.v5_features import (
    V5FeatureUnavailable,
    build_v5_candidate_inputs,
)
from digital_spotter.inference.v5_preprocessing import V5Preprocessor
from digital_spotter.inference.v5_model import V5ModelRuntime, V5Prediction
from digital_spotter.inference.v5_shadow import V5ShadowEvaluator


PACKAGE = Path(__file__).resolve().parents[2] / "models" / "digital_spotter_v5"


def _rep(*, exercise_id: int = 0, quality: Quality = Quality.GOOD) -> CompletedRep:
    vision = {
        **{
            f"Vis_{joint}_{axis}": 0.1 * (index + 1)
            for index, joint in enumerate((
                "L_Shoulder", "R_Shoulder", "L_Hip", "R_Hip",
                "L_Knee", "R_Knee", "L_Ankle", "R_Ankle",
            ))
            for axis in ("X", "Y")
        },
        "Angle_Trunk_Inclination": 12.0,
        "Angle_Hip_Flexion_L": 40.0,
        "Angle_Hip_Flexion_R": 35.0,
        "Angle_Knee_Flexion_L": 80.0,
        "Angle_Knee_Flexion_R": 70.0,
        "Angle_Ankle_Dorsiflexion_L": 15.0,
        "Angle_Ankle_Dorsiflexion_R": 10.0,
    }
    imu = {
        "acceleration_m_s2_x": 3.0,
        "acceleration_m_s2_y": 4.0,
        "acceleration_m_s2_z": 0.0,
        "angular_velocity_rad_s_x": 0.1,
        "angular_velocity_rad_s_y": 0.2,
        "angular_velocity_rad_s_z": 0.3,
    }
    phases = tuple(
        PhaseRecord(
            phase=number,
            name=PHASE_NAMES[exercise_id][number - 1],
            started_monotonic_ns=number * 1_000_000,
            ended_monotonic_ns=number * 1_000_000 + 100_000,
            captured_monotonic_ns=number * 1_000_000 + 50_000,
            frame_count=5,
            vision=vision,
            imu=imu,
            quality=quality,
        )
        for number in (1, 2, 3)
    )
    event = RepEvent(
        rep_id=uuid4(),
        rep_number=1,
        exercise_contract_version="v5-research-video-rule-1",
        event=RepTransition.COMPLETED,
        captured_monotonic_ns=3_100_000,
        quality=quality,
    )
    return CompletedRep(None, event, phases)


def test_candidate_has_exact_stage8_order_values_and_preprocessing_shape() -> None:
    preprocessor = V5Preprocessor(PACKAGE)
    candidate = build_v5_candidate_inputs(
        _rep(), exercise_id=0, load_kg=42.5, preprocessor=preprocessor
    )

    assert tuple(candidate.phases[0]) == ("phase", *preprocessor.temporal_features)
    assert candidate.context == {"Exercise_ID": 0, "Load_kg": 42.5}
    assert candidate.phases[0]["Hip_Flexion_Asymmetry"] == 5.0
    assert candidate.phases[0]["Knee_Flexion_Asymmetry"] == 10.0
    assert candidate.phases[0]["Ankle_Dorsiflexion_Asymmetry"] == 5.0
    assert candidate.phases[0]["Knee_Hip_Coupling_L"] == pytest.approx(80 / (40 + 1e-6))
    assert candidate.phases[0]["Knee_Hip_Coupling_R"] == pytest.approx(70 / (35 + 1e-6))
    assert candidate.phases[0]["IMU_Acc_Magnitude"] == 5.0
    assert candidate.phases[0]["IMU_Gyro_X"] == 0.1
    assert [phase["phase"] for phase in candidate.phases] == [1, 2, 3]
    temporal, context = preprocessor.transform(candidate.phases, candidate.context)
    assert temporal.shape == (1, 3, 29)
    assert context.shape == (1, 2)


def test_missing_or_degraded_imu_fails_closed() -> None:
    preprocessor = V5Preprocessor(PACKAGE)
    rep = _rep()
    missing = replace(rep, phases=(replace(rep.phases[0], imu=None), *rep.phases[1:]))
    with pytest.raises(V5FeatureUnavailable, match="IMU unavailable"):
        build_v5_candidate_inputs(missing, exercise_id=0, load_kg=42.5, preprocessor=preprocessor)
    degraded = replace(rep, event=rep.event.model_copy(update={"quality": Quality.UNAVAILABLE}))
    with pytest.raises(V5FeatureUnavailable, match="rep quality"):
        build_v5_candidate_inputs(degraded, exercise_id=0, load_kg=42.5, preprocessor=preprocessor)


def test_invalid_phase_or_context_fails_closed() -> None:
    preprocessor = V5Preprocessor(PACKAGE)
    rep = _rep(exercise_id=1)
    wrong_phase = replace(rep, phases=(replace(rep.phases[0], phase=2), *rep.phases[1:]))
    with pytest.raises(V5FeatureUnavailable, match="phase order"):
        build_v5_candidate_inputs(wrong_phase, exercise_id=1, load_kg=42.5, preprocessor=preprocessor)
    with pytest.raises(V5FeatureUnavailable, match="load"):
        build_v5_candidate_inputs(rep, exercise_id=1, load_kg=None, preprocessor=preprocessor)


def test_shadow_runs_only_reference_inference_for_complete_candidate() -> None:
    class RuntimeStub:
        preprocessor = V5Preprocessor(PACKAGE)

        def __init__(self) -> None:
            self.calls = 0

        def predict_reference_only(self, phases, context):
            self.calls += 1
            assert tuple(phases[0]) == ("phase", *self.preprocessor.temporal_features)
            assert context == {"Exercise_ID": 0, "Load_kg": 42.5}
            return V5Prediction(0.2, 0.3, 1, 0.25, reference_only=True)

        def predict(self, phases, context):
            raise AssertionError("validated prediction must not run")

    runtime = RuntimeStub()
    outcome = V5ShadowEvaluator(runtime).evaluate(_rep(), exercise_id=0, load_kg=42.5)

    assert runtime.calls == 1
    assert outcome.state == "executed_reference_only"
    assert outcome.reason is None
    assert outcome.model_version == "digital_spotter_v5_scope_faithful"
    assert outcome.experimental is True
    assert "probability" not in str(outcome)


def test_shadow_skips_incomplete_rep_without_model_invocation() -> None:
    class RuntimeStub:
        preprocessor = V5Preprocessor(PACKAGE)

        def predict_reference_only(self, phases, context):
            raise AssertionError("incomplete rep must not reach model")

    rep = _rep()
    missing = replace(rep, phases=(replace(rep.phases[0], imu=None), *rep.phases[1:]))
    outcome = V5ShadowEvaluator(RuntimeStub()).evaluate(missing, exercise_id=0, load_kg=42.5)

    assert outcome.state == "unavailable"
    assert outcome.reason == "candidate_features_unavailable"
    assert outcome.experimental is True


def test_shadow_can_invoke_frozen_model_without_exposing_a_score() -> None:
    outcome = V5ShadowEvaluator(V5ModelRuntime(PACKAGE)).evaluate(
        _rep(), exercise_id=0, load_kg=42.5
    )

    assert outcome.state == "executed_reference_only"
    assert outcome.experimental is True
    assert "probability" not in str(outcome)


def test_shadow_refuses_an_unflagged_model_result() -> None:
    class UnsafeRuntime:
        preprocessor = V5Preprocessor(PACKAGE)

        def predict_reference_only(self, phases, context):
            return V5Prediction(0.2, 0.3, 1, 0.25, reference_only=False)

    outcome = V5ShadowEvaluator(UnsafeRuntime()).evaluate(
        _rep(), exercise_id=0, load_kg=42.5
    )

    assert outcome.state == "unavailable"
    assert outcome.reason == "runtime_policy_mismatch"
