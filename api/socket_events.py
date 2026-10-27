"""
api/socket_events.py
Purpose: WebSocket event handlers and emitters using Flask-SocketIO.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""

import logging
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask_socketio import emit
from config.constants import WEBSOCKET_EVENTS

logger = logging.getLogger(__name__)

# Track connected clients
_connected_clients = set()
_streaming = False


def register_events(socketio):
    """Register all WebSocket event handlers.

    Args:
        socketio: Flask-SocketIO instance.

    Side Effects:
        Registers connect, disconnect, start_stream, stop_stream, ping.
    """

    @socketio.on("connect")
    def on_connect():
        """Handle client connection."""
        from flask import request
        _connected_clients.add(request.sid)
        logger.info("Client connected: %s (total: %d)",
                     request.sid, len(_connected_clients))
        emit(WEBSOCKET_EVENTS["SYSTEM_STATUS"], {
            "camera_ok": True,
            "model_ok": True,
            "fps": 0,
            "latency_ms": 0,
            "clients": len(_connected_clients),
        })

    @socketio.on("disconnect")
    def on_disconnect():
        """Handle client disconnection."""
        from flask import request
        _connected_clients.discard(request.sid)
        logger.info("Client disconnected: %s (total: %d)",
                     request.sid, len(_connected_clients))

    @socketio.on("start_stream")
    def on_start_stream():
        """Client requests live pose data streaming."""
        global _streaming
        _streaming = True
        logger.info("Stream started by client")
        emit("stream_started", {"status": "ok"})

    @socketio.on("stop_stream")
    def on_stop_stream():
        """Client stops live pose data streaming."""
        global _streaming
        _streaming = False
        logger.info("Stream stopped by client")
        emit("stream_stopped", {"status": "ok"})

    @socketio.on("ping")
    def on_ping():
        """Heartbeat response."""
        emit("pong", {"timestamp": int(time.time() * 1000)})


def emit_pose_data(socketio, data):
    """Emit pose data to all connected clients.

    Args:
        socketio: Flask-SocketIO instance.
        data: Dict with landmarks, angles, fps, timestamp_ms.

    Side Effects:
        Broadcasts pose_data event to all clients.
    """
    if _streaming and _connected_clients:
        socketio.emit(WEBSOCKET_EVENTS["POSE_DATA"], data)


def emit_inference_result(socketio, result):
    """Emit inference result to all clients.

    Args:
        socketio: Flask-SocketIO instance.
        result: Dict with label, confidence, is_bad_form, rep_number.
    """
    socketio.emit(WEBSOCKET_EVENTS["INFERENCE_RESULT"], result)


def emit_rep_complete(socketio, rep_data):
    """Emit rep complete event.

    Args:
        socketio: Flask-SocketIO instance.
        rep_data: Dict with rep_number, phase, angles.
    """
    socketio.emit(WEBSOCKET_EVENTS["REP_COMPLETE"], rep_data)


def emit_session_update(socketio, stats):
    """Emit session stats update.

    Args:
        socketio: Flask-SocketIO instance.
        stats: Dict with total_reps, good_reps, bad_reps.
    """
    socketio.emit(WEBSOCKET_EVENTS["SESSION_UPDATE"], stats)


def emit_system_status(socketio, status):
    """Emit system status to all clients.

    Args:
        socketio: Flask-SocketIO instance.
        status: Dict with camera_ok, model_ok, fps, latency_ms.
    """
    socketio.emit(WEBSOCKET_EVENTS["SYSTEM_STATUS"], status)


def is_streaming():
    """Check if any client is requesting live data.
    Returns:
        bool: True if streaming is active.
    """
    return _streaming


def client_count():
    """Get number of connected clients.
    Returns:
        int: Connected client count.
    """
    return len(_connected_clients)
