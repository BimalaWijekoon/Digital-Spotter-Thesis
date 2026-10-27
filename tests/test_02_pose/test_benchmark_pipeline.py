"""Tests for bounded benchmark behavior and CLI result signaling."""

import sys

from scripts import benchmark_pipeline


def test_pose_error_returns_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(
        benchmark_pipeline,
        "run_pose",
        lambda *args, **kwargs: {"mode": "pose", "error": "stream stalled"},
    )
    monkeypatch.setattr(sys, "argv", ["benchmark", "--mode", "pose"])

    assert benchmark_pipeline.main() == 2
    assert "stream stalled" in capsys.readouterr().out


def test_sysmon_success_returns_zero(monkeypatch, capsys):
    monkeypatch.setattr(
        benchmark_pipeline,
        "run_sysmon",
        lambda seconds: {"mode": "sysmon", "window_s": seconds},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["benchmark", "--mode", "sysmon", "--seconds", "1"],
    )

    assert benchmark_pipeline.main() == 0
    assert '"mode": "sysmon"' in capsys.readouterr().out
