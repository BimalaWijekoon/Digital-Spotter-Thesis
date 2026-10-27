"""
inference/preprocessor.py
Purpose: Load and apply the joblib StandardScaler from training.
         Falls back to identity transform if scaler.pkl not available.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import logging
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config

logger = logging.getLogger(__name__)


class Preprocessor:
    """Wrapper for preprocessing chain (winsorize -> impute -> scale) with graceful fallback."""

    def __init__(self):
        """Initialize Preprocessor with no artifacts loaded."""
        self._scaler = None
        self._is_loaded = False
        self._is_mock = False
        self._winsor_bounds = None
        self._feature_medians = None

    def load(self, scaler_path=None, winsor_path=None, medians_path=None):
        """Load scaler, winsor bounds, and feature medians.

        Each artifact degrades independently and gracefully: if winsor_bounds
        or feature_medians are missing, that step is skipped (passthrough)
        rather than failing — matching the existing fallback philosophy of
        this codebase (mock mode rather than crash).

        Args:
            scaler_path: Path to scaler.save. Uses Config.PATHS.SCALER_PKL.
            winsor_path: Path to winsor_bounds.save. Uses Config.PATHS.WINSOR_BOUNDS.
            medians_path: Path to feature_medians.save. Uses Config.PATHS.FEATURE_MEDIANS.

        Returns:
            bool: True if the scaler (the only load-bearing artifact) loaded.
        """
        import joblib
        scaler_path = Path(scaler_path) if scaler_path else Config.PATHS.SCALER_PKL
        winsor_path = Path(winsor_path) if winsor_path else Config.PATHS.WINSOR_BOUNDS
        medians_path = Path(medians_path) if medians_path else Config.PATHS.FEATURE_MEDIANS

        scaler_ok = self._load_scaler(scaler_path, joblib)
        self._winsor_bounds = self._load_optional_dict(winsor_path, joblib, "winsor bounds")
        self._feature_medians = self._load_optional_dict(medians_path, joblib, "feature medians")
        return scaler_ok

    def _load_optional_dict(self, path, joblib_module, label):
        """Load a joblib dict artifact, returning None on any failure.

        Args:
            path: Path to the .save file.
            joblib_module: Imported joblib module (passed in to avoid
                re-importing per call).
            label: Human-readable name for log messages.

        Returns:
            dict or None.
        """
        if not path.exists():
            logger.warning("%s file not found: %s — skipping this step", label, path)
            return None
        try:
            d = joblib_module.load(str(path))
            logger.info("%s loaded from %s (%d entries)", label, path, len(d))
            return d
        except Exception as e:
            logger.error("Failed to load %s: %s — skipping this step", label, e)
            return None

    def _load_scaler(self, scaler_path, joblib_module):
        if not scaler_path.exists():
            logger.warning("Scaler file not found: %s — using identity transform", scaler_path)
            self._is_mock = True
            self._is_loaded = True
            return False

        try:
            self._scaler = joblib_module.load(str(scaler_path))
            self._is_loaded = True
            self._is_mock = False
            logger.info("Scaler loaded from %s", scaler_path)
            return True
        except Exception as e:
            logger.error("Failed to load scaler: %s", e)
            self._is_mock = True
            self._is_loaded = True
            return False

    def transform(self, features):
        """Apply the same scaling as training to a feature vector.

        Args:
            features: numpy.ndarray of shape (N,) or (M, N) where
                N is the number of features.

        Returns:
            numpy.ndarray: Scaled features, same shape as input.
                Returns input unchanged if in mock mode.
        """
        if not self._is_loaded:
            self.load()

        features = np.array(features, dtype=np.float32)

        if self._is_mock or self._scaler is None:
            return features

        # Handle both 1D and 2D inputs
        if features.ndim == 1:
            return self._scaler.transform(
                features.reshape(1, -1)
            ).flatten().astype(np.float32)
        else:
            return self._scaler.transform(features).astype(np.float32)

    def is_loaded(self):
        """Check if scaler is loaded (including mock mode).

        Returns:
            bool: True if scaler is ready for use.
        """
        return self._is_loaded

    @property
    def is_mock(self):
        """Check if using identity transform fallback.

        Returns:
            bool: True if no real scaler was loaded.
        """
        return self._is_mock

    def apply_preprocessing(self, sequence):
        """Run the full v4 preprocessing chain: winsorize -> impute -> scale.

        This order is NOT arbitrary — it exactly matches Section 8 of the
        training notebook (winsorization cell runs before the median
        imputation cell, which runs before the StandardScaler fit/transform
        cell). Reversing the order would clip values that imputation should
        have replaced first, or scale before bounds are enforced.

        Args:
            sequence: numpy.ndarray, shape (4, num_features) — the model-ready
                sequence from SequenceBuffer.get_model_sequence().

        Returns:
            numpy.ndarray: Shape (4, num_features), preprocessed and ready
                for the TFLite interpreter (still needs a batch dim added by
                the caller — see lstm_runner.py).
        """
        sequence = np.array(sequence, dtype=np.float32)

        if self._winsor_bounds:
            sequence = self._apply_winsor(sequence)

        if self._feature_medians:
            sequence = self._apply_imputation(sequence)

        return self.transform(sequence)  # existing scaler-only method, unchanged

    def _apply_winsor(self, sequence):
        """Clip IMU columns to the saved [lo, hi] bounds per feature.

        Args:
            sequence: numpy.ndarray, shape (timesteps, num_features).

        Returns:
            numpy.ndarray: Same shape, IMU columns clipped.
        """
        from config.constants import FEATURE_ORDER
        out = sequence.copy()
        for fname, (lo, hi) in self._winsor_bounds.items():
            if fname in FEATURE_ORDER:
                fidx = FEATURE_ORDER.index(fname)
                out[:, fidx] = np.clip(out[:, fidx], lo, hi)
        return out

    def _apply_imputation(self, sequence):
        """Fill NaN values with the saved per-feature training medians.

        Args:
            sequence: numpy.ndarray, shape (timesteps, num_features).

        Returns:
            numpy.ndarray: Same shape, NaN replaced.
        """
        from config.constants import FEATURE_ORDER
        out = sequence.copy()
        nan_mask = np.isnan(out)
        if not nan_mask.any():
            return out
        for fname, median in self._feature_medians.items():
            if fname in FEATURE_ORDER:
                fidx = FEATURE_ORDER.index(fname)
                col = out[:, fidx]
                col[np.isnan(col)] = median
                out[:, fidx] = col
        return out
