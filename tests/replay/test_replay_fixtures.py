from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from digital_spotter.contracts import MonotonicNanoseconds
from digital_spotter.core import (
    ReplayAdapter,
    ReplayClock,
    ReplayFixtureError,
    load_replay_fixture,
)


FIXTURES = Path(__file__).parents[1] / "fixtures" / "replay" / "v1"


def _load(name: str):
    return load_replay_fixture(FIXTURES / name)


def _write_mutation(tmp_path: Path, name: str, mutate):
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    mutate(raw)
    video_path = raw.get("video", {}).get("path")
    if video_path and ".." not in Path(video_path).parts:
        shutil.copyfile(FIXTURES / video_path, tmp_path / video_path)
    path = tmp_path / name
    path.write_text(json.dumps(raw), encoding="utf-8")
    return load_replay_fixture(path)


def _move_second_event_before_first(raw):
    event = raw["events"][1]
    event["captured_monotonic_ns"] = 1_500_000
    event["created_monotonic_ns"] = 1_520_000
    event["payload"]["captured_monotonic_ns"] = 1_500_000
    event["payload"]["arrival_monotonic_ns"] = 1_510_000


def test_normal_replay_is_bitwise_deterministic_and_never_real():
    fixture = _load("synthetic_normal_rep.json")
    adapter = ReplayAdapter(fixture)

    first = adapter.run()
    second = adapter.run()

    assert first == second
    assert first.event_digest_sha256 == (
        "90620503de89823e0e63822fa82bb530910817ddd1680c22f0a68ab72c55a046"
    )
    assert first.phase_sequence == ("eccentric", "bottom", "lockout")
    assert first.analysis_labels == ("synthetic_expected_good_form",)
    assert adapter.mode == "replay"
    assert adapter.is_real is False
    assert adapter.is_simulated is True
    assert adapter.persistence_allowed is False
    assert first.is_real is False
    assert first.persistence_allowed is False
    assert fixture.video.kind == "synthetic"
    assert fixture.video.frame_count == 3
    assert fixture.video.captured_monotonic_ns[1] == 1_030_000


@pytest.mark.parametrize(
    ("fixture_name", "gaps", "resets"),
    [
        ("synthetic_imu_gap.json", 2, 0),
        ("synthetic_clock_reset.json", 0, 1),
    ],
)
def test_gap_and_reset_fixtures_match_exact_expectations(fixture_name, gaps, resets):
    result = ReplayAdapter(_load(fixture_name)).run()

    assert result.imu_gap_count == gaps
    assert result.clock_reset_count == resets


def test_corrupted_event_type_is_rejected():
    fixture = _load("invalid_event_type.json")

    with pytest.raises(ReplayFixtureError, match="invalid replay event"):
        ReplayAdapter(fixture).run()


def test_declared_gap_must_match_sequence(tmp_path):
    fixture = _write_mutation(
        tmp_path,
        "synthetic_imu_gap.json",
        lambda raw: raw["events"][1]["payload"].update(gap_count_since_previous=1),
    )

    with pytest.raises(ReplayFixtureError, match="declared IMU gap"):
        ReplayAdapter(fixture).run(verify_expected=False)


def test_boot_change_requires_explicit_reset_state(tmp_path):
    fixture = _write_mutation(
        tmp_path,
        "synthetic_clock_reset.json",
        lambda raw: raw["events"][1]["payload"].update(clock_state="acquiring"),
    )

    with pytest.raises(ReplayFixtureError, match="new IMU boot_id"):
        ReplayAdapter(fixture).run(verify_expected=False)


def test_duplicate_event_and_backward_clock_are_rejected(tmp_path):
    duplicate = _write_mutation(
        tmp_path,
        "synthetic_imu_gap.json",
        lambda raw: raw["events"][1].update(event_id=raw["events"][0]["event_id"]),
    )
    with pytest.raises(ReplayFixtureError, match="duplicate replay event_id"):
        ReplayAdapter(duplicate).run(verify_expected=False)

    backward_raw = json.loads(
        (FIXTURES / "synthetic_imu_gap.json").read_text(encoding="utf-8")
    )
    _move_second_event_before_first(backward_raw)
    backward_path = tmp_path / "backward.json"
    backward_path.write_text(json.dumps(backward_raw), encoding="utf-8")
    backward = load_replay_fixture(backward_path)
    with pytest.raises(ReplayFixtureError, match="cannot move backward"):
        ReplayAdapter(backward).run(verify_expected=False)


def test_expected_result_tampering_fails_closed(tmp_path):
    fixture = _write_mutation(
        tmp_path,
        "synthetic_normal_rep.json",
        lambda raw: raw["expected"].update(analysis_labels=["tampered"]),
    )

    with pytest.raises(ReplayFixtureError, match="analysis_labels"):
        ReplayAdapter(fixture).run()


def test_replay_clock_never_sleeps_or_moves_backward():
    clock = ReplayClock()
    clock.advance_to(MonotonicNanoseconds(10))
    assert clock.now_ns() == 10

    with pytest.raises(ReplayFixtureError, match="cannot move backward"):
        clock.advance_to(MonotonicNanoseconds(9))


def test_all_committed_fixtures_are_synthetic_and_contain_no_person_data():
    for path in FIXTURES.glob("*.json"):
        fixture = load_replay_fixture(path)
        assert fixture.provenance.kind == "synthetic"
        assert fixture.provenance.contains_person_data is False
        assert fixture.provenance.consent == "not_applicable_synthetic"
        assert fixture.video.kind in {"none", "synthetic"}


def test_fixture_schema_rejects_video_traversal(tmp_path):
    raw = json.loads((FIXTURES / "synthetic_normal_rep.json").read_text(encoding="utf-8"))
    raw["video"]["path"] = "../person.mp4"
    raw["video"]["sha256"] = "a" * 64
    path = tmp_path / "traversal.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ReplayFixtureError, match="safe fixture-relative"):
        load_replay_fixture(path)


def test_synthetic_video_must_exist_and_match_its_hash(tmp_path):
    raw = json.loads((FIXTURES / "synthetic_normal_rep.json").read_text(encoding="utf-8"))
    path = tmp_path / "missing-video.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReplayFixtureError, match="artifact not found"):
        load_replay_fixture(path)

    shutil.copyfile(
        FIXTURES / "synthetic_motion_4x4.y4m",
        tmp_path / "synthetic_motion_4x4.y4m",
    )
    raw["video"]["sha256"] = "a" * 64
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ReplayFixtureError, match="hash mismatch"):
        load_replay_fixture(path)
