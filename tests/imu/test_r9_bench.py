from __future__ import annotations

from digital_spotter.contracts import ClockState
from digital_spotter.imu.r9_agent import R9ConnectionState
from digital_spotter.imu.r9_bench import _failed_checks


def test_r9_bench_gate_accepts_clean_fifty_hz_stream():
    assert _failed_checks(
        duration_s=10.0,
        samples_received=500,
        state=R9ConnectionState.STREAMING,
        observed_rate_hz=50.0,
        latest_sample_age_ms=10.0,
        sequence_gaps=0,
        duplicate_packets=0,
        invalid_packets=0,
        notification_drops=0,
        publisher_failures=0,
        connection_failures=0,
        reconnects=0,
        minimum_reconnects=0,
        maximum_reconnects=0,
        i2c_errors=0,
        clock_gate_drops=0,
        clock_state=ClockState.SYNCHRONIZED,
        clock_error_p95_ns=5_000_000,
        clock_monotonic_correction_samples=0,
    ) == ()


def test_r9_bench_gate_names_each_failure():
    assert _failed_checks(
        duration_s=10.0,
        samples_received=100,
        state=R9ConnectionState.DEGRADED,
        observed_rate_hz=40.0,
        latest_sample_age_ms=300.0,
        sequence_gaps=1,
        duplicate_packets=2,
        invalid_packets=3,
        notification_drops=4,
        publisher_failures=5,
        connection_failures=3,
        reconnects=6,
        minimum_reconnects=0,
        maximum_reconnects=0,
        i2c_errors=7,
        clock_gate_drops=8,
        clock_state=ClockState.DEGRADED,
        clock_error_p95_ns=25_000_000,
        clock_monotonic_correction_samples=2,
    ) == (
        "sample_count_below_45_hz",
        "runtime_not_streaming",
        "sample_rate_outside_48_52_hz",
        "latest_sample_stale",
        "sequence_gaps_detected",
        "duplicate_packets_detected",
        "invalid_packets_detected",
        "notification_queue_drops",
        "publisher_failures",
        "excessive_connection_failures",
        "reconnect_count_above_expected",
        "i2c_errors_detected",
        "clock_gate_drops_during_measurement",
        "clock_not_synchronized",
        "clock_error_p95_not_below_20_ms",
        "clock_capture_monotonic_corrections",
    )


def test_r9_bench_gate_accepts_one_expected_controlled_reconnect():
    assert _failed_checks(
        duration_s=10.0,
        samples_received=500,
        state=R9ConnectionState.STREAMING,
        observed_rate_hz=50.0,
        latest_sample_age_ms=10.0,
        sequence_gaps=0,
        duplicate_packets=0,
        invalid_packets=0,
        notification_drops=0,
        publisher_failures=0,
        connection_failures=0,
        reconnects=1,
        minimum_reconnects=1,
        maximum_reconnects=3,
        i2c_errors=0,
        clock_gate_drops=0,
        clock_state=ClockState.SYNCHRONIZED,
        clock_error_p95_ns=5_000_000,
        clock_monotonic_correction_samples=0,
    ) == ()
