"""
tests/test_04_api/test_websocket.py
Purpose: Test WebSocket connection and events.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-15
"""
import sys
import pytest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.config import Config
from database.db import close_connection


@pytest.fixture
def socketio_client(tmp_path):
    original_db = Config.PATHS.DATABASE
    Config.PATHS.DATABASE = tmp_path / "test_ws.db"
    close_connection()

    from api.app import create_app, socketio
    app = create_app()
    app.config["TESTING"] = True
    client = socketio.test_client(app)
    yield client

    client.disconnect()
    close_connection()
    Config.PATHS.DATABASE = original_db


class TestWebSocket:
    def test_websocket_connects(self, socketio_client):
        assert socketio_client.is_connected()

    def test_websocket_receives_system_status(self, socketio_client):
        received = socketio_client.get_received()
        events = [r["name"] for r in received]
        assert "system_status" in events

    def test_websocket_ping_pong(self, socketio_client):
        socketio_client.emit("ping")
        received = socketio_client.get_received()
        events = [r["name"] for r in received]
        assert "pong" in events
