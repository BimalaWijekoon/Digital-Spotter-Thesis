"""
tests/test_04_api/test_endpoints.py
Purpose: Test REST API endpoints via Flask test client.
Author: bimalawijekoon
Version: 1.0.0
Last Modified: 2026-06-22
"""
import sys
import json
import pytest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.config import Config
from database.db import close_connection


class _MockSessionManager:
    """Minimal stub that satisfies routes.py's SessionManager API."""

    def __init__(self):
        self._session_id = None
        self.is_active = False
        self.frame_processor = None  # health endpoint checks this

    @property
    def session_id(self):
        return self._session_id

    def start_session(self, exercise_id=0, notes=None, height_cm=None,
                       weight_kg=None, ftr=None, load_kg=None):
        from database.queries import create_session
        name = Config.EXERCISES.get_name(exercise_id)
        self._session_id = create_session(
            exercise_id, name, notes,
            height_cm=height_cm or 175.0,
            weight_kg=weight_kg or 75.0,
            ftr=ftr or 1.20,
        )
        self.is_active = True
        return self._session_id

    def stop_session(self):
        from database.queries import end_session, get_session_stats
        end_session(self._session_id)
        stats = get_session_stats(self._session_id)
        self._session_id = None
        self.is_active = False
        return stats


@pytest.fixture
def client(tmp_path):
    """Create Flask test client with temp database and stub SessionManager."""
    original_db = Config.PATHS.DATABASE
    Config.PATHS.DATABASE = tmp_path / "test_api.db"
    close_connection()

    from api.app import create_app
    from api.routes import set_session_manager
    app = create_app()
    app.config["TESTING"] = True

    mock_sm = _MockSessionManager()
    with app.app_context():
        set_session_manager(mock_sm)

    with app.test_client() as c:
        yield c

    close_connection()
    set_session_manager(None)
    Config.PATHS.DATABASE = original_db

class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "status" in data
        assert "uptime_s" in data

    def test_health_has_camera_field(self, client):
        data = client.get("/api/health").get_json()
        assert "camera" in data
        assert "model" in data


class TestStatusEndpoint:
    def test_status_returns_valid_schema(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "streaming" in data
        assert "fps" in data
        assert "latency_ms" in data


class TestSessionEndpoints:
    def test_session_start_returns_session_id(self, client):
        resp = client.post("/api/session/start",
                           json={"exercise_id": 0})
        assert resp.status_code == 201
        data = resp.get_json()
        assert "session_id" in data
        assert data["session_id"] > 0

    def test_session_stop_returns_stats(self, client):
        start = client.post("/api/session/start",
                            json={"exercise_id": 0}).get_json()
        sid = start["session_id"]
        resp = client.post("/api/session/stop",
                           json={"session_id": sid})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_reps" in data

    def test_session_stop_no_id_returns_400(self, client):
        resp = client.post("/api/session/stop", json={})
        assert resp.status_code == 400

    def test_session_get_returns_reps(self, client):
        start = client.post("/api/session/start",
                            json={"exercise_id": 0}).get_json()
        sid = start["session_id"]
        resp = client.get(f"/api/session/{sid}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "session" in data
        assert "reps" in data

    def test_sessions_list(self, client):
        client.post("/api/session/start", json={"exercise_id": 0})
        client.post("/api/session/start", json={"exercise_id": 1})
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["sessions"]) == 2


class TestInferenceEndpoint:
    def test_inference_test_returns_result(self, client):
        resp = client.post("/api/inference/test")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "label" in data
        assert "confidence" in data
        assert "latency_ms" in data
