"""
tests/test_03_inference/test_model_load.py
Purpose: Test LSTMRunner model loading and mock inference.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""
import sys
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from inference.lstm_runner import LSTMRunner, InferenceResult


class TestModelLoad:
    def test_lstm_runner_initializes(self):
        runner = LSTMRunner()
        assert runner is not None

    def test_lstm_runner_loads_mock(self):
        runner = LSTMRunner()
        runner.load()
        assert runner.is_loaded()
        assert runner.is_mock

    def test_lstm_runner_placeholder_returns_result(self):
        runner = LSTMRunner()
        runner.load()
        seq = np.random.randn(3, 38).astype(np.float32)
        result = runner.predict(seq)
        assert isinstance(result, InferenceResult)
        assert result.label in ["Good Form", "Bad Form"]
        assert 0.0 <= result.confidence <= 1.0

    def test_inference_result_to_dict(self):
        r = InferenceResult(label="Good Form", confidence=0.87,
                            is_bad_form=False, latency_ms=12.5)
        d = r.to_dict()
        assert d["label"] == "Good Form"
        assert d["confidence"] == 0.87
        assert d["is_bad_form"] is False
