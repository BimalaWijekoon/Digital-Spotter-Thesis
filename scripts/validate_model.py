#!/usr/bin/env python3
"""
scripts/validate_model.py
Purpose: Validate TFLite model file — checks input/output shapes,
         runs a sample inference, and reports compatibility.
Author: bimalawijekoon
Version: 1.1.0
"""

import sys
import time
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config


def load_interpreter(model_path):
    """Load a TFLite interpreter with Flex delegate support.

    On this Pi the Flex delegate in ai_edge_litert depends on tensorflow's
    shared libraries being loaded into process memory first. Importing
    tensorflow before creating the ai_edge_litert interpreter is what makes
    FlexTensorListReserve (required by Bidirectional LSTM) work. Without
    this pre-import, ai_edge_litert fails with 'Select TensorFlow op(s)
    not supported'. With it, the delegate loads successfully.

    tf.lite.Interpreter itself fails on this TF 2.16.2 AWS aarch64 build
    due to FULLY_CONNECTED version 12 being too new for the bundled kernel
    table — so we use tf.lite only to warm up the shared libs, then
    hand off to ai_edge_litert for the actual inference.

    Args:
        model_path: Path-like, location of the .tflite file.

    Returns:
        Allocated interpreter instance.

    Raises:
        RuntimeError: If no runtime can load the model.
    """
    model_path_str = str(model_path)

    # Step 1 — warm up tensorflow shared libs in process memory.
    # This is what allows ai_edge_litert's Flex delegate to find
    # FlexTensorListReserve and other SELECT_TF_OPS at runtime.
    try:
        import tensorflow as tf  # noqa: F401 — side-effect import
    except ImportError:
        print("  Warning: tensorflow not installed — Flex delegate may fail")

    # Step 2 — use ai_edge_litert (correct kernel table for this model).
    # tf.lite.Interpreter itself fails on FULLY_CONNECTED version 12
    # with TF 2.16.2 AWS aarch64, so ai_edge_litert is the right runtime.
    try:
        import ai_edge_litert.interpreter as litert
        interp = litert.Interpreter(model_path=model_path_str)
        interp.allocate_tensors()
        print("  Runtime: ai_edge_litert + tensorflow Flex delegate")
        return interp
    except Exception as e:
        print(f"  ai_edge_litert failed: {e}")

    raise RuntimeError(
        "No TFLite runtime could load the model.\n"
        "Ensure both tensorflow==2.16.2 and ai-edge-litert are installed:\n"
        "  pip install tensorflow==2.16.2\n"
        "  pip install ai-edge-litert"
    )


def validate():
    model_path = Config.PATHS.MODEL_TFLITE
    scaler_path = Config.PATHS.SCALER_PKL

    print("=" * 50)
    print("Digital Spotter — Model Validator")
    print("=" * 50)

    print(f"\nModel path: {model_path}")
    print(f"  Exists: {model_path.exists()}")

    print(f"\nScaler path: {scaler_path}")
    print(f"  Exists: {scaler_path.exists()}")

    if not model_path.exists():
        print("\n[!] Model file not found — using mock inference.")
        print("    Place model_quantized.tflite in models/ directory.")
        return

    interpreter = load_interpreter(model_path)

    inp = interpreter.get_input_details()
    out = interpreter.get_output_details()

    print(f"\nInput shape:  {inp[0]['shape']}")
    print(f"Input dtype:  {inp[0]['dtype']}")
    print(f"Output shape: {out[0]['shape']}")
    print(f"Output dtype: {out[0]['dtype']}")

    # Run sample inference
    dummy = np.random.randn(*inp[0]['shape']).astype(np.float32)
    interpreter.set_tensor(inp[0]['index'], dummy)

    start = time.perf_counter()
    interpreter.invoke()
    elapsed = (time.perf_counter() - start) * 1000

    result = interpreter.get_tensor(out[0]['index'])
    print(f"\nSample output: {result}")
    print(f"Inference time: {elapsed:.2f} ms")
    print("\n✓ Model validation passed!")


if __name__ == "__main__":
    validate()