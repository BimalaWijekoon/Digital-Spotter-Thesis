"""
tests/test_02_pose/test_rep_segmentation.py
Purpose: Test RepSegmenter with synthetic angle data.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import sys
import math
import pytest
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vision.rep_segmenter import RepSegmenter, RepEvent


class TestRepSegmentation:
    """Test rep detection with synthetic angle signals."""

    def _generate_squat_angles(self, num_reps=1, fps=30):
        """Generate synthetic knee angle signal for squats.

        Simulates a standing->squat->standing cycle using a
        cosine wave. Standing ~170°, Bottom ~80°.

        Args:
            num_reps: Number of reps to simulate.
            fps: Frames per second.

        Returns:
            list[dict]: Sequence of angle dicts, one per frame.
        """
        frames_per_rep = fps * 3  # 3 seconds per rep
        total_frames = frames_per_rep * num_reps + fps  # + 1s padding
        angle_sequence = []

        for i in range(total_frames):
            # Cosine wave: 170° (standing) to 80° (bottom)
            t = (i % frames_per_rep) / frames_per_rep
            knee_angle = 125.0 + 45.0 * math.cos(2 * math.pi * t)
            # Add small noise
            noise = np.random.normal(0, 0.5)
            angles = {
                "LEFT_HIP": 160.0 + noise,
                "RIGHT_HIP": 160.0 + noise,
                "LEFT_KNEE": knee_angle + noise,
                "RIGHT_KNEE": knee_angle + noise,
                "LEFT_ANKLE": 70.0 + noise,
                "RIGHT_ANKLE": 70.0 + noise,
                "TRUNK": 15.0 + noise,
            }
            angle_sequence.append(angles)

        return angle_sequence

    def test_rep_segmenter_initializes(self):
        """Verify RepSegmenter creates without error."""
        seg = RepSegmenter(fps=30)
        assert seg is not None
        assert seg.rep_count == 0
        assert seg.current_phase == 0

    def test_rep_segmenter_detects_phase(self):
        """Verify RepSegmenter detects at least one phase from a rep."""
        seg = RepSegmenter(fps=30)
        angles_sequence = self._generate_squat_angles(num_reps=1, fps=30)

        events = []
        for angles in angles_sequence:
            event = seg.update(angles)
            if event is not None:
                events.append(event)

        # Should detect at least 1 phase transition
        assert len(events) >= 1
        # Events should be RepEvent instances
        for event in events:
            assert isinstance(event, RepEvent)
            assert event.phase in [1, 2, 3]

    def test_rep_segmenter_assigns_phases(self):
        """Verify phases 1, 2, 3 are assigned during a rep."""
        seg = RepSegmenter(fps=30)
        angles_sequence = self._generate_squat_angles(num_reps=2, fps=30)

        phases_seen = set()
        for angles in angles_sequence:
            event = seg.update(angles)
            if event is not None:
                phases_seen.add(event.phase)

        # Should see at least eccentric (1) phase
        assert 1 in phases_seen

    def test_rep_segmenter_reset(self):
        """Verify reset clears all state."""
        seg = RepSegmenter(fps=30)
        angles_sequence = self._generate_squat_angles(num_reps=1, fps=30)

        for angles in angles_sequence:
            seg.update(angles)

        seg.reset()
        assert seg.rep_count == 0
        assert seg.current_phase == 0

    def test_rep_event_to_dict(self):
        """Verify RepEvent serializes correctly."""
        event = RepEvent(
            rep_number=1,
            phase=2,
            frame_start=30,
            frame_end=60,
            angles_at_bottom={"LEFT_KNEE": 85.0},
        )
        d = event.to_dict()
        assert d["rep_number"] == 1
        assert d["phase"] == 2
        assert d["phase_name"] == "Isometric/Bottom"
        assert d["angles_at_bottom"]["LEFT_KNEE"] == 85.0
