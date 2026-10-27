"""
tests/test_03_inference/test_full_inference.py
Purpose: Test full inference pipeline: features -> buffer -> predict.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""
import sys
import time
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from inference.feature_engineer import FeatureEngineer
from inference.sequence_buffer import SequenceBuffer
from inference.lstm_runner import LSTMRunner


class TestFullInference:
    def _make_landmarks(self):
        return {
            "LEFT_HIP": (0.42, 0.55, 0.0, 0.9),
            "RIGHT_HIP": (0.58, 0.55, 0.0, 0.9),
            "LEFT_KNEE": (0.41, 0.72, 0.0, 0.9),
            "RIGHT_KNEE": (0.59, 0.72, 0.0, 0.9),
            "LEFT_SHOULDER": (0.4, 0.3, 0.0, 0.9),
            "RIGHT_SHOULDER": (0.6, 0.3, 0.0, 0.9),
            "LEFT_ANKLE": (0.40, 0.90, 0.0, 0.9),
            "RIGHT_ANKLE": (0.60, 0.90, 0.0, 0.9),
        }

    def _make_angles(self):
        return {
            "LEFT_HIP": 95.0, "RIGHT_HIP": 93.0,
            "LEFT_KNEE": 88.0, "RIGHT_KNEE": 87.0,
            "LEFT_ANKLE": 72.0, "RIGHT_ANKLE": 71.0,
            "TRUNK": 14.0,
        }

    def test_feature_engineer_returns_40_features(self):
        fe = FeatureEngineer()
        features = fe.engineer(self._make_landmarks(), self._make_angles())
        assert features.shape == (40,)
        assert features.dtype == np.float32

    def test_feature_engineer_asymmetry_calculation(self):
        fe = FeatureEngineer()
        angles = self._make_angles()
        asym = fe._compute_asymmetry_features(angles)
        assert asym.shape == (3,)
        assert asym[0] == abs(angles["LEFT_HIP"] - angles["RIGHT_HIP"])

    def test_full_pipeline_mock(self):
        fe = FeatureEngineer()
        buf = SequenceBuffer()
        runner = LSTMRunner()
        runner.load()

        for phase in [1, 2, 3]:
            ctx = {"rep_phase": phase, "exercise_id": 0}
            features = fe.engineer(
                self._make_landmarks(), self._make_angles(), context=ctx
            )
            buf.push(phase, features)

        assert buf.is_ready()
        result = runner.predict(buf.get_model_sequence())
        assert result.label in ["Good Form", "Bad Form"]

    def test_inference_latency_under_25ms(self):
        runner = LSTMRunner()
        runner.load()
        seq = np.random.randn(4, 40).astype(np.float32)
        result = runner.predict(seq)
        assert result.latency_ms < 25
