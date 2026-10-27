"""Tests for the temporary canonical FastAPI launcher."""

from config.config import Config
from scripts import run_server


def test_launcher_uses_api_configuration(monkeypatch):
    captured = {}

    def fake_run(app_path, **kwargs):
        captured["app_path"] = app_path
        captured.update(kwargs)

    monkeypatch.setattr(run_server.uvicorn, "run", fake_run)

    run_server.main()

    assert captured == {
        "app_path": "scripts.dashboard.main:app",
        "host": Config.API.HOST,
        "port": Config.API.PORT,
        "reload": False,
    }
