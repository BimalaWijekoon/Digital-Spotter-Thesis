"""
tests/test_03_inference/test_preprocessor.py
Purpose: Test Preprocessor load and transform operations.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-22
"""
import sys
import numpy as np
from pathlib import Path
import tempfile
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from inference.preprocessor import Preprocessor


class TestPreprocessor:
    def test_preprocessor_loads_and_is_ready(self):
        """Preprocessor.load() must succeed regardless of whether real
        artifacts exist. is_loaded() must be True in all cases."""
        p = Preprocessor()
        p.load()
        assert p.is_loaded()

    def test_mock_mode_uses_identity_transform(self):
        """When pointed at a non-existent scaler path, Preprocessor falls back
        to identity transform — output equals input."""
        p = Preprocessor()
        # Force mock by pointing all paths to a temp dir with no files
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            p.load(
                scaler_path=tmp / "no_scaler.save",
                winsor_path=tmp / "no_winsor.save",
                medians_path=tmp / "no_medians.save",
            )
        assert p.is_mock
        features = np.ones(40, dtype=np.float32) * 5.0
        result = p.transform(features)
        assert np.allclose(result, features)

    def test_transform_2d(self):
        """transform() must preserve shape for 2D (sequence) inputs."""
        p = Preprocessor()
        p.load()
        features = np.ones((4, 40), dtype=np.float32)
        result = p.transform(features)
        assert result.shape == (4, 40)
