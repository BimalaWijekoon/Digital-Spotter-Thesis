"""
inference/lstm_runner.py
Purpose: Load TFLite model and run inference on (4, 40) sequence.
         Falls back to mock predictions if model file unavailable.
Author: bimalawijekoon
Version: 2.0.0
Last Modified: 2026-06-22
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config
from inference.preprocessor import Preprocessor

logger = logging.getLogger(__name__)

# Pre-import tensorflow to load its shared libraries into process memory.
# ai_edge_litert's Flex delegate (needed for FlexTensorListReserve from
# Bidirectional LSTM) depends on these shared libs being present at runtime.
# Without this, ai_edge_litert fails with "Select TensorFlow op(s) not
# supported" even though the Flex delegate is technically available.
try:
    import tensorflow as _tf_preload  # noqa: F401 — side-effect only
except Exception:
    pass

# TFLite runtime — ai_edge_litert has the correct op kernel table for this
# model (FULLY_CONNECTED v12). tf.lite.Interpreter from the TF 2.16.2 AWS
# aarch64 build fails on that op version, so it is the last resort only.
try:
    import ai_edge_litert.interpreter as tflite
    TFLITE_AVAILABLE = True
except ImportError:
    try:
        import tensorflow as tf
        tflite = tf.lite
        TFLITE_AVAILABLE = True
    except ImportError:
        try:
            import tflite_runtime.interpreter as tflite
            TFLITE_AVAILABLE = True
        except ImportError:
            TFLITE_AVAILABLE = False
            logger.warning(
                "TFLite runtime not available — using mock inference"
            )


@dataclass
class InferenceResult:
    """Result from LSTM model inference.

    Attributes:
        label: Prediction label — 'Good Form' or 'Bad Form'.
        confidence: Sigmoid output 0.0-1.0.
        is_bad_form: True if confidence >= threshold.
        latency_ms: Inference time in milliseconds.
        is_mock: True if no real TFLite model was loaded.
    """
    label: str = "Good Form"
    confidence: float = 0.5
    is_bad_form: bool = False
    latency_ms: float = 0.0
    is_mock: bool = False

    def to_dict(self):
        """Convert to dictionary for JSON serialization.

        Returns:
            dict: All fields as a dictionary.
        """
        return {
            "label": self.label,
            "confidence": round(self.confidence, 4),
            "is_bad_form": self.is_bad_form,
            "latency_ms": round(self.latency_ms, 2),
            "is_mock": self.is_mock,
        }


class LSTMRunner:
    """TFLite LSTM model loader and inference engine.

    Loads a quantized TFLite model for form classification.
    Falls back to mock predictions (random confidence) if
    model file is not available.
    """

    def __init__(self):
        """Initialize LSTMRunner with no model loaded."""
        self._interpreter = None
        self._input_details = None
        self._output_details = None
        self._preprocessor = Preprocessor()
        self._is_loaded = False
        self._is_mock = False

    def load(self, model_path=None, scaler_path=None):
        """Load TFLite model and scaler from files.

        Args:
            model_path: Path to .tflite model file. Uses
                Config.PATHS.MODEL_TFLITE if None.
            scaler_path: Path to scaler.pkl. Uses
                Config.PATHS.SCALER_PKL if None.

        Returns:
            bool: True if real model loaded, False if using mock.

        Side Effects:
            Loads model and scaler into memory.
        """
        model_path = Path(model_path) if model_path else (
            Config.PATHS.MODEL_TFLITE
        )
        scaler_path = Path(scaler_path) if scaler_path else (
            Config.PATHS.SCALER_PKL
        )

        # Load preprocessor artifacts
        self._preprocessor.load(scaler_path=scaler_path)

        # Load model
        if not model_path.exists():
            logger.warning(
                "Model not found: %s — using mock inference",
                model_path
            )
            # TODO: PHASE_4 - Replace placeholder model with actual
            # model_quantized.tflite from training
            self._is_mock = True
            self._is_loaded = True
            return False

        if not TFLITE_AVAILABLE:
            logger.warning("TFLite unavailable — using mock inference")
            self._is_mock = True
            self._is_loaded = True
            return False

        try:
            # Pre-load tensorflow shared libs so ai_edge_litert's Flex
            # delegate can find FlexTensorListReserve at allocate_tensors().
            # Must happen in the same call context as Interpreter(), not just
            # at module import time.
            try:
                import tensorflow as _tf  # noqa: F401
            except Exception:
                pass

            self._interpreter = tflite.Interpreter(
                model_path=str(model_path)
            )
            self._interpreter.allocate_tensors()
            self._input_details = (
                self._interpreter.get_input_details()
            )
            self._output_details = (
                self._interpreter.get_output_details()
            )
            self._is_loaded = True
            self._is_mock = False
            logger.info("LSTM model loaded from %s", model_path)
            return True

        except Exception as e:
            logger.error("Failed to load model: %s", e)
            self._is_mock = True
            self._is_loaded = True
            return False

    def predict(self, sequence):
        """Run inference on a (4, 40) sequence (already includes the delta
        timestep — pass SequenceBuffer.get_model_sequence(), not get_sequence()).

        Args:
            sequence: numpy.ndarray of shape (4, 40) —
                4 phase feature vectors.

        Returns:
            InferenceResult: Prediction with label, confidence,
                and latency.

        Side Effects:
            None (pure inference).
        """
        if not self._is_loaded:
            self.load()

        start_time = time.perf_counter()

        if self._is_mock:
            return self._mock_predict(start_time)

        try:
            preprocessed = self._preprocess(sequence)

            self._interpreter.set_tensor(
                self._input_details[0]["index"],
                preprocessed,
            )
            self._interpreter.invoke()

            output = self._interpreter.get_tensor(
                self._output_details[0]["index"]
            )

            # Sigmoid output: probability of bad form
            confidence = float(output[0][0])
            is_bad = confidence >= Config.INFERENCE.DECISION_THRESHOLD
            label = (
                Config.INFERENCE.BAD_FORM_LABEL if is_bad
                else Config.INFERENCE.GOOD_FORM_LABEL
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            return InferenceResult(
                label=label,
                confidence=confidence,
                is_bad_form=is_bad,
                latency_ms=elapsed_ms,
                is_mock=False,
            )

        except Exception as e:
            logger.error("Inference error: %s", e)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return InferenceResult(latency_ms=elapsed_ms)

    def is_loaded(self):
        """Check if model is loaded (including mock mode).

        Returns:
            bool: True if ready for inference.
        """
        return self._is_loaded

    @property
    def is_mock(self):
        """Check if using mock predictions.

        Returns:
            bool: True if no real model loaded.
        """
        return self._is_mock

    def _preprocess(self, sequence):
        """Run winsor->impute->scale, then add batch dimension.

        Args:
            sequence: numpy.ndarray of shape (4, 40) — see predict() docstring.

        Returns:
            numpy.ndarray: Shape (1, 4, 40) float32 tensor.
        """
        sequence = np.array(sequence, dtype=np.float32)
        processed = self._preprocessor.apply_preprocessing(sequence)
        return processed.reshape(1, *processed.shape).astype(np.float32)

    def _mock_predict(self, start_time):
        """Generate mock prediction for development.

        Produces a random confidence score, biased toward good form.

        Args:
            start_time: perf_counter timestamp.

        Returns:
            InferenceResult: Mock result with random confidence.
        """
        # Bias toward good form (70% chance)
        confidence = np.random.beta(2, 5)  # Skewed toward 0
        is_bad = confidence >= Config.INFERENCE.DECISION_THRESHOLD
        label = (
            Config.INFERENCE.BAD_FORM_LABEL if is_bad
            else Config.INFERENCE.GOOD_FORM_LABEL
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return InferenceResult(
            label=label,
            confidence=float(confidence),
            is_bad_form=is_bad,
            latency_ms=elapsed_ms,
            is_mock=True,
        )