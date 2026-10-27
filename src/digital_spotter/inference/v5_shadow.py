"""Opt-in V5 research invocation; never a scored result or feedback source."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from digital_spotter.core.rep_phases import CompletedRep

from .v5_features import V5FeatureUnavailable, build_v5_candidate_inputs
from .v5_model import MODEL_VERSION, V5Prediction
from .v5_preprocessing import V5Preprocessor


class _ReferenceRuntime(Protocol):
    preprocessor: V5Preprocessor

    def predict_reference_only(self, phases, context) -> V5Prediction: ...


@dataclass(frozen=True)
class V5ShadowOutcome:
    rep_number: int
    state: str
    reason: str | None
    model_version: str | None
    experimental: bool = True


class V5ShadowEvaluator:
    """Exercise the frozen V5 path without exposing a prediction or saving it."""

    def __init__(self, runtime: _ReferenceRuntime) -> None:
        self.runtime = runtime

    def evaluate(
        self,
        rep: CompletedRep,
        *,
        exercise_id: int,
        load_kg: float,
    ) -> V5ShadowOutcome:
        try:
            candidate = build_v5_candidate_inputs(
                rep,
                exercise_id=exercise_id,
                load_kg=load_kg,
                preprocessor=self.runtime.preprocessor,
            )
        except V5FeatureUnavailable:
            return V5ShadowOutcome(
                rep.event.rep_number, "unavailable", "candidate_features_unavailable", None
            )

        prediction = self.runtime.predict_reference_only(
            candidate.phases, candidate.context
        )
        if not prediction.reference_only or prediction.model_version != MODEL_VERSION:
            return V5ShadowOutcome(
                rep.event.rep_number, "unavailable", "runtime_policy_mismatch", None
            )
        return V5ShadowOutcome(
            rep.event.rep_number, "executed_reference_only", None, MODEL_VERSION
        )
