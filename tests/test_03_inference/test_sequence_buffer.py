"""
tests/test_03_inference/test_sequence_buffer.py
Purpose: Test SequenceBuffer fill, ready, and reset operations.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import sys
import pytest
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from inference.sequence_buffer import SequenceBuffer


class TestSequenceBuffer:
    """Test SequenceBuffer operations."""

    def test_buffer_initializes_empty(self):
        """Verify buffer starts with zero count."""
        buf = SequenceBuffer(sequence_length=3)
        assert buf.count == 0
        assert not buf.is_ready()

    def test_sequence_buffer_fills_correctly(self):
        """Verify buffer tracks filled phases."""
        buf = SequenceBuffer(sequence_length=3)
        features = np.random.randn(40).astype(np.float32)

        buf.push(1, features)
        assert buf.count == 1
        assert not buf.is_ready()

        buf.push(2, features)
        assert buf.count == 2

        buf.push(3, features)
        assert buf.count == 3
        assert buf.is_ready()

    def test_get_sequence_returns_correct_shape(self):
        """Verify get_sequence returns (3, 40) array."""
        buf = SequenceBuffer(sequence_length=3)

        for phase in [1, 2, 3]:
            features = np.ones(40, dtype=np.float32) * phase
            buf.push(phase, features)

        seq = buf.get_sequence()
        assert seq.shape == (3, 40)
        assert np.allclose(seq[0], np.ones(40) * 1)
        assert np.allclose(seq[2], np.ones(40) * 3)

    def test_get_model_sequence_adds_delta(self):
        """Verify get_model_sequence appends the delta phase3-phase1."""
        from config.constants import FEATURE_ORDER
        buf = SequenceBuffer(sequence_length=3)
        for phase in [1, 2, 3]:
            buf.push(phase, np.ones(40, dtype=np.float32) * phase)

        model_seq = buf.get_model_sequence(decel_ratio_idx=FEATURE_ORDER.index("Velocity_Decel_Ratio"), decel_ratio_value=1.5)
        assert model_seq.shape == (4, 40)
        # Delta = phase 3 (all 3s) - phase 1 (all 1s) = all 2s (except decel_ratio)
        expected_delta = np.ones(40) * 2
        expected_delta[FEATURE_ORDER.index("Velocity_Decel_Ratio")] = 1.5
        assert np.allclose(model_seq[3], expected_delta)

    def test_sequence_buffer_resets(self):
        """Verify reset clears all state."""
        buf = SequenceBuffer(sequence_length=3)
        for phase in [1, 2, 3]:
            buf.push(phase, np.random.randn(40))

        assert buf.is_ready()
        buf.reset()
        assert not buf.is_ready()
        assert buf.count == 0

    def test_invalid_phase_raises(self):
        """Verify invalid phase_id raises ValueError."""
        buf = SequenceBuffer(sequence_length=3)
        with pytest.raises(ValueError):
            buf.push(0, np.zeros(40))
        with pytest.raises(ValueError):
            buf.push(4, np.zeros(40))

    def test_push_same_phase_overwrites(self):
        """Verify pushing same phase overwrites without incrementing count."""
        buf = SequenceBuffer(sequence_length=3)
        buf.push(1, np.ones(40))
        buf.push(1, np.ones(40) * 2)
        assert buf.count == 1
        seq = buf.get_sequence()
        assert np.allclose(seq[0], np.ones(40) * 2)
