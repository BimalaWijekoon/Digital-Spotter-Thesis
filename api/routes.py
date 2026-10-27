"""
api/routes.py
Purpose: All REST API endpoints as Flask Blueprint.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import logging
import time
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Blueprint, jsonify, request

from config.config import Config
from config.constants import WEBSOCKET_EVENTS
from database.queries import (
    create_session, end_session, get_session,
    get_session_reps, get_recent_sessions, get_session_stats,
)
from inference.lstm_runner import LSTMRunner, InferenceResult

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")

_session_manager = None

def set_session_manager(sm):
    """Set the shared SessionManager instance.
    Args:
        sm: SessionManager instance from the integration layer.
    """
    global _session_manager
    _session_manager = sm


@api_bp.route("/health", methods=["GET"])
def health():
    """System health check endpoint.
    Returns:
        JSON with status, camera, model, and uptime info.
    """
    from api.app import get_uptime
    camera_ok = False
    model_loaded = False
    if _session_manager:
        camera_ok = _session_manager.frame_processor is not None
        model_loaded = True  # We assume true if session manager exists for now

    if model_loaded and camera_ok:
        status = "ok"
    elif model_loaded or camera_ok:
        status = "degraded"
    else:
        status = "degraded"

    return jsonify({
        "status": status,
        "camera": camera_ok,
        "model": model_loaded,
        "uptime_s": get_uptime(),
    })


@api_bp.route("/status", methods=["GET"])
def status():
    """Full system status endpoint.
    Returns:
        JSON with streaming state, session info, fps, latency.
    """
    fps = 0.0
    latency = 0.0
    is_streaming = False
    is_active = False
    session_id = None

    if _session_manager:
        is_streaming = _session_manager.frame_processor is not None
        is_active = _session_manager.is_active
        session_id = _session_manager.session_id
        
        if _session_manager.frame_processor:
            latest = _session_manager.frame_processor.get_latest()
            if latest:
                fps = latest.fps
                latency = latest.processing_time_ms

    return jsonify({
        "streaming": is_streaming,
        "session_active": is_active,
        "current_session_id": session_id,
        "fps": round(fps, 1),
        "latency_ms": round(latency, 2),
    })


@api_bp.route("/session/start", methods=["POST"])
def session_start():
    """Start a new training session.
    Body:
        exercise_id (int): 0=Squat, 1=Deadlift.
        notes (str, optional): Session notes.
    Returns:
        JSON with session_id and started_at.
    """
    data = request.get_json(silent=True) or {}
    exercise_id = data.get("exercise_id", 0)
    notes = data.get("notes")
    
    # New v4 parameters
    height_cm = data.get("height_cm")
    weight_kg = data.get("weight_kg")
    ftr = data.get("ftr")
    load_kg = data.get("load_kg")

    if not _session_manager:
        return jsonify({"error": "SessionManager not ready"}), 503

    session_id = _session_manager.start_session(
        exercise_id=exercise_id,
        notes=notes,
        height_cm=height_cm,
        weight_kg=weight_kg,
        ftr=ftr,
        load_kg=load_kg
    )

    session = get_session(session_id)
    return jsonify({
        "session_id": session_id,
        "started_at": session.started_at if session else "",
    }), 201


@api_bp.route("/session/stop", methods=["POST"])
def session_stop():
    """End current session and save stats.
    Body:
        session_id (int): Session to end.
    Returns:
        JSON with session_id and final rep counts.
    """
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"error": "session_id required"}), 400

    if not _session_manager:
        return jsonify({"error": "SessionManager not ready"}), 503

    if _session_manager.session_id == session_id:
        stats = _session_manager.stop_session()
        return jsonify({
            "session_id": session_id,
            "total_reps": stats.get("total_reps", 0),
            "good_reps": stats.get("good_reps", 0),
            "bad_reps": stats.get("bad_reps", 0),
        })
    else:
        success = end_session(session_id)
        if not success:
            return jsonify({"error": "Session not found"}), 404

        session = get_session(session_id)
        return jsonify({
            "session_id": session_id,
            "total_reps": session.total_reps if session else 0,
            "good_reps": session.good_reps if session else 0,
            "bad_reps": session.bad_reps if session else 0,
        })


@api_bp.route("/session/<int:session_id>", methods=["GET"])
def session_detail(session_id):
    """Get session details and rep history.
    Args:
        session_id: Session ID from URL path.
    Returns:
        JSON with session object and reps list.
    """
    session = get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    reps = get_session_reps(session_id)
    stats = get_session_stats(session_id)

    return jsonify({
        "session": session.to_dict(),
        "reps": [r.to_dict() for r in reps],
        "stats": stats,
    })


@api_bp.route("/sessions", methods=["GET"])
def sessions_list():
    """List recent sessions.
    Query params:
        limit (int): Max sessions to return (default 10).
    Returns:
        JSON with sessions list.
    """
    limit = request.args.get("limit", 10, type=int)
    sessions = get_recent_sessions(limit=limit)

    return jsonify({
        "sessions": [s.to_dict() for s in sessions],
    })


@api_bp.route("/inference/test", methods=["POST"])
def inference_test():
    """Run inference on a (4,40) dummy sequence — for development/validation.

    Exercises the full LSTMRunner.predict() path including TFLite interpreter
    invocation (or mock fallback). Useful for verifying the model artifact
    loads and runs without needing a camera or live session.

    Returns:
        JSON with label, confidence, latency_ms, and is_mock flag.
    """
    runner = LSTMRunner()
    runner.load()
    dummy_sequence = np.zeros((4, 40), dtype=np.float32)
    result = runner.predict(dummy_sequence)
    return jsonify({
        "label": result.label,
        "confidence": round(result.confidence, 4),
        "latency_ms": round(result.latency_ms, 2),
        "is_mock": result.is_mock,
    })


def generate_frames():
    """Generator for MJPEG streaming.
    Yields JPEG-encoded bytes from the latest annotated frame.
    """
    import cv2
    while True:
        if not _session_manager or not _session_manager.frame_processor:
            time.sleep(0.1)
            continue

        _, frame = _session_manager.frame_processor.get_latest()
        if frame is None:
            time.sleep(0.05)
            continue

        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue

        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        # Throttle yield loop to roughly 30 FPS to save CPU
        time.sleep(1/30.0)


@api_bp.route("/video_feed")
def video_feed():
    """MJPEG streaming endpoint for the dashboard video player."""
    from flask import Response
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )
