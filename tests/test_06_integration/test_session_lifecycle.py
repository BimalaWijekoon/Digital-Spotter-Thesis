"""
tests/test_06_integration/test_session_lifecycle.py
Purpose: Test complete session lifecycle through SessionManager.
Author: bimalawijekoon
Version: 1.0.0
"""
import sys
import pytest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.config import Config
from database.db import init_db, close_connection
from integration.session_manager import SessionManager


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    original = Config.PATHS.DATABASE
    Config.PATHS.DATABASE = tmp_path / "test_integration.db"
    close_connection()
    init_db()
    yield
    close_connection()
    Config.PATHS.DATABASE = original


class TestSessionLifecycle:
    def test_session_start_returns_id(self):
        mgr = SessionManager()
        sid = mgr.start_session(exercise_id=0)
        assert sid > 0
        assert mgr.is_active

    def test_session_stop_returns_stats(self):
        mgr = SessionManager()
        mgr.start_session(exercise_id=0)
        stats = mgr.stop_session()
        assert "total_reps" in stats
        assert not mgr.is_active

    def test_session_rep_count_starts_zero(self):
        mgr = SessionManager()
        mgr.start_session(exercise_id=0)
        assert mgr.rep_count == 0

    def test_stop_without_start(self):
        mgr = SessionManager()
        stats = mgr.stop_session()
        assert stats == {}
