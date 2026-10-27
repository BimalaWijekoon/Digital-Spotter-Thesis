"""Short real-hardware gate for the canonical R9 runtime."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import sys
import time
from dataclasses import asdict, dataclass

from digital_spotter.contracts import ClockState
from digital_spotter.imu.r9_agent import R9AgentCore, R9ConnectionState
from digital_spotter.imu.r9_protocol import (
    DEVICE_ADDRESS,
    DEVICE_NAME,
    RESEARCH_DEVICE_ID,
)
from digital_spotter.imu.r9_runtime import R9IMUAgentRuntime
from digital_spotter.imu.r9_transport import R9BleakTransport


@dataclass(frozen=True)
class R9BenchSummary:
    evidence_environment: str
    hardware_simulated: bool
    device_id: str
    device_name: str
    device_address: str
    requested_duration_s: float
    observed_duration_s: float
    controlled_reconnect: bool
    samples_received: int
    observed_rate_hz: float | None
    latest_sample_age_ms: float | None
    sequence_gaps: int
    duplicate_packets: int
    invalid_packets: int
    notification_drops: int
    recovery_invalid_packets: int
    recovery_notification_drops: int
    publisher_failures: int
    connection_failures: int
    reconnects: int
    i2c_errors: int
    clock_sync_wait_s: float
    clock_state: str
    clock_drift_ppm: float | None
    clock_error_p95_ms: float | None
    capture_to_arrival_p50_ms: float | None
    capture_to_arrival_p95_ms: float | None
    clock_model_error_ms: float
    clock_fit_points: int
    clock_exchanges_accepted: int
    clock_exchanges_rejected: int
    clock_gate_drops: int
    recovery_clock_gate_drops: int
    clock_exchange_rtt_p95_ms: float | None
    clock_causal_cap_samples: int
    clock_monotonic_correction_samples: int
    passed: bool
    failed_checks: tuple[str, ...]


class CountingPublisher:
    def __init__(self) -> None:
        self.count = 0
        self.first_event = asyncio.Event()
        self.clock_errors_ns: list[int] = []
        self.capture_lags_ns: list[int] = []

    async def send(self, event) -> None:
        self.count += 1
        self.clock_errors_ns.append(event.payload.estimated_clock_error_ns)
        self.capture_lags_ns.append(
            int(event.payload.arrival_monotonic_ns)
            - int(event.payload.captured_monotonic_ns)
        )
        self.first_event.set()

    async def close(self) -> None:
        return None


def _failed_checks(
    *,
    duration_s: float,
    samples_received: int,
    state: R9ConnectionState,
    observed_rate_hz: float | None,
    latest_sample_age_ms: float | None,
    sequence_gaps: int,
    duplicate_packets: int,
    invalid_packets: int,
    notification_drops: int,
    publisher_failures: int,
    connection_failures: int,
    reconnects: int,
    minimum_reconnects: int,
    maximum_reconnects: int,
    i2c_errors: int,
    clock_gate_drops: int,
    clock_state: ClockState,
    clock_error_p95_ns: int | None,
    clock_monotonic_correction_samples: int,
) -> tuple[str, ...]:
    failed: list[str] = []
    if samples_received < int(duration_s * 45.0):
        failed.append("sample_count_below_45_hz")
    if state is not R9ConnectionState.STREAMING:
        failed.append("runtime_not_streaming")
    if observed_rate_hz is None or not 48.0 <= observed_rate_hz <= 52.0:
        failed.append("sample_rate_outside_48_52_hz")
    if latest_sample_age_ms is None or latest_sample_age_ms > 250.0:
        failed.append("latest_sample_stale")
    if sequence_gaps:
        failed.append("sequence_gaps_detected")
    if duplicate_packets:
        failed.append("duplicate_packets_detected")
    if invalid_packets:
        failed.append("invalid_packets_detected")
    if notification_drops:
        failed.append("notification_queue_drops")
    if publisher_failures:
        failed.append("publisher_failures")
    if connection_failures > 2:
        failed.append("excessive_connection_failures")
    if reconnects < minimum_reconnects:
        failed.append("reconnect_count_below_expected")
    if reconnects > maximum_reconnects:
        failed.append("reconnect_count_above_expected")
    if i2c_errors:
        failed.append("i2c_errors_detected")
    if clock_gate_drops:
        failed.append("clock_gate_drops_during_measurement")
    if clock_state is not ClockState.SYNCHRONIZED:
        failed.append("clock_not_synchronized")
    if clock_error_p95_ns is None or clock_error_p95_ns >= 20_000_000:
        failed.append("clock_error_p95_not_below_20_ms")
    if clock_monotonic_correction_samples:
        failed.append("clock_capture_monotonic_corrections")
    return tuple(failed)


def _nearest_rank(values: list[int], quantile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


async def run_bench(args: argparse.Namespace) -> R9BenchSummary:
    core = R9AgentCore(device_id=args.device_id)
    publisher = CountingPublisher()
    runtime = R9IMUAgentRuntime(
        core=core,
        transport=R9BleakTransport(
            expected_name=args.device_name,
            expected_address=args.device_address,
            scan_timeout_s=args.scan_timeout,
            connect_timeout_s=args.connect_timeout,
        ),
        publisher=publisher,
    )
    runtime_task = asyncio.create_task(runtime.run())
    started = 0.0
    ended = 0.0
    start_count = 0
    measurement_baseline = None
    clock_measurement_index = 0
    clock_monotonic_correction_baseline = 0
    clock_sync_wait_s = 0.0
    health = None
    try:
        await asyncio.wait_for(
            publisher.first_event.wait(),
            timeout=args.scan_timeout + args.connect_timeout + 5.0,
        )
        if args.exercise_reconnect:
            await asyncio.sleep(2.0)
            count_before_disconnect = publisher.count
            await runtime.transport.disconnect()
            reconnect_deadline = (
                time.monotonic() + args.scan_timeout + args.connect_timeout + 5.0
            )
            stable_since = None
            stable_start_count = 0
            stable_reconnects = -1
            while time.monotonic() < reconnect_deadline:
                counters = core.counters()
                current_health = core.health(now_monotonic_ns=time.monotonic_ns())
                stable_now = (
                    counters.reconnects >= 1
                    and runtime.transport.is_connected
                    and current_health.state is R9ConnectionState.STREAMING
                    and publisher.count > count_before_disconnect
                )
                if stable_now:
                    if (
                        stable_since is None
                        or counters.reconnects != stable_reconnects
                    ):
                        stable_reconnects = counters.reconnects
                        stable_since = time.monotonic()
                        stable_start_count = publisher.count
                else:
                    stable_since = None
                if (
                    stable_since is not None
                    and time.monotonic() - stable_since >= 3.0
                    and publisher.count - stable_start_count >= 100
                ):
                    break
                await asyncio.sleep(0.05)
            else:
                raise RuntimeError("controlled R9 reconnect did not recover")
        clock_wait_started = time.monotonic()
        clock_deadline = clock_wait_started + args.clock_sync_timeout
        while time.monotonic() < clock_deadline:
            if core.health(
                now_monotonic_ns=time.monotonic_ns()
            ).clock_state is ClockState.SYNCHRONIZED:
                break
            await asyncio.sleep(0.05)
        clock_sync_wait_s = time.monotonic() - clock_wait_started
        measurement_baseline = core.counters()
        start_count = publisher.count
        clock_measurement_index = len(publisher.clock_errors_ns)
        clock_monotonic_correction_baseline = (
            core.clock_mapper.monotonic_correction_samples
        )
        started = time.monotonic()
        await asyncio.sleep(args.duration)
        ended = time.monotonic()
        health = core.health(now_monotonic_ns=time.monotonic_ns())
    finally:
        runtime.stop()
        await asyncio.wait_for(runtime_task, timeout=10.0)

    if health is None:
        raise RuntimeError("R9 runtime produced no measurable health snapshot")
    if measurement_baseline is None:
        raise RuntimeError("R9 runtime did not establish a measurement baseline")
    observed_duration = ended - started
    final_counters = core.counters()
    samples_received = publisher.count - start_count
    measured_sequence_gaps = (
        final_counters.sequence_gaps - measurement_baseline.sequence_gaps
    )
    measured_duplicates = (
        final_counters.packets_duplicate - measurement_baseline.packets_duplicate
    )
    measured_invalid = (
        final_counters.packets_rejected - measurement_baseline.packets_rejected
    )
    measured_drops = (
        final_counters.notification_drops - measurement_baseline.notification_drops
    )
    measured_publisher_failures = (
        final_counters.publisher_failures - measurement_baseline.publisher_failures
    )
    measured_clock_gate_drops = (
        final_counters.clock_gate_drops - measurement_baseline.clock_gate_drops
    )
    measured_monotonic_corrections = (
        core.clock_mapper.monotonic_correction_samples
        - clock_monotonic_correction_baseline
    )
    measured_clock_errors = publisher.clock_errors_ns[clock_measurement_index:]
    measured_capture_lags = publisher.capture_lags_ns[clock_measurement_index:]
    clock_error_p95_ns = _nearest_rank(measured_clock_errors, 0.95)
    capture_lag_p50_ns = _nearest_rank(measured_capture_lags, 0.50)
    capture_lag_p95_ns = _nearest_rank(measured_capture_lags, 0.95)
    accepted_clock_rtts = [
        diagnostic.round_trip_ns
        for diagnostic in core.clock_mapper.exchange_diagnostics
        if diagnostic.accepted
    ]
    clock_rtt_p95_ns = _nearest_rank(accepted_clock_rtts, 0.95)
    failed = _failed_checks(
        duration_s=observed_duration,
        samples_received=samples_received,
        state=health.state,
        observed_rate_hz=health.sample_rate_hz,
        latest_sample_age_ms=health.latest_sample_age_ms,
        sequence_gaps=measured_sequence_gaps,
        duplicate_packets=measured_duplicates,
        invalid_packets=measured_invalid,
        notification_drops=measured_drops,
        publisher_failures=measured_publisher_failures,
        connection_failures=health.counters.connection_failures,
        reconnects=health.counters.reconnects,
        minimum_reconnects=1 if args.exercise_reconnect else 0,
        maximum_reconnects=3 if args.exercise_reconnect else 0,
        i2c_errors=health.i2c_errors,
        clock_gate_drops=measured_clock_gate_drops,
        clock_state=health.clock_state,
        clock_error_p95_ns=clock_error_p95_ns,
        clock_monotonic_correction_samples=measured_monotonic_corrections,
    )
    return R9BenchSummary(
        evidence_environment="E3_real_hardware",
        hardware_simulated=False,
        device_id=args.device_id,
        device_name=args.device_name,
        device_address=args.device_address,
        requested_duration_s=args.duration,
        observed_duration_s=observed_duration,
        controlled_reconnect=args.exercise_reconnect,
        samples_received=samples_received,
        observed_rate_hz=health.sample_rate_hz,
        latest_sample_age_ms=health.latest_sample_age_ms,
        sequence_gaps=measured_sequence_gaps,
        duplicate_packets=measured_duplicates,
        invalid_packets=measured_invalid,
        notification_drops=measured_drops,
        recovery_invalid_packets=measurement_baseline.packets_rejected,
        recovery_notification_drops=measurement_baseline.notification_drops,
        publisher_failures=measured_publisher_failures,
        connection_failures=health.counters.connection_failures,
        reconnects=health.counters.reconnects,
        i2c_errors=health.i2c_errors,
        clock_sync_wait_s=clock_sync_wait_s,
        clock_state=health.clock_state.value,
        clock_drift_ppm=health.clock_drift_ppm,
        clock_error_p95_ms=(
            None if clock_error_p95_ns is None else clock_error_p95_ns / 1_000_000.0
        ),
        capture_to_arrival_p50_ms=(
            None if capture_lag_p50_ns is None else capture_lag_p50_ns / 1_000_000.0
        ),
        capture_to_arrival_p95_ms=(
            None if capture_lag_p95_ns is None else capture_lag_p95_ns / 1_000_000.0
        ),
        clock_model_error_ms=health.estimated_clock_error_ms,
        clock_fit_points=health.clock_fit_points,
        clock_exchanges_accepted=health.counters.clock_exchanges_accepted,
        clock_exchanges_rejected=health.counters.clock_exchanges_rejected,
        clock_gate_drops=measured_clock_gate_drops,
        recovery_clock_gate_drops=measurement_baseline.clock_gate_drops,
        clock_exchange_rtt_p95_ms=(
            None if clock_rtt_p95_ns is None else clock_rtt_p95_ns / 1_000_000.0
        ),
        clock_causal_cap_samples=core.clock_mapper.causal_cap_samples,
        clock_monotonic_correction_samples=measured_monotonic_corrections,
        passed=not failed,
        failed_checks=failed,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ds-imu-r9-bench")
    parser.add_argument("--device-id", default=RESEARCH_DEVICE_ID)
    parser.add_argument("--device-name", default=DEVICE_NAME)
    parser.add_argument("--device-address", default=DEVICE_ADDRESS)
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--scan-timeout", type=float, default=15.0)
    parser.add_argument("--connect-timeout", type=float, default=20.0)
    parser.add_argument("--clock-sync-timeout", type=float, default=12.0)
    parser.add_argument(
        "--exercise-reconnect",
        action="store_true",
        help="drop one established link and require automatic recovery before measuring",
    )
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if not 10.0 <= args.duration <= 300.0:
        raise ValueError("duration must be between 10 and 300 seconds")
    if not 1.0 <= args.scan_timeout <= 120.0:
        raise ValueError("scan timeout must be between 1 and 120 seconds")
    if not 1.0 <= args.connect_timeout <= 120.0:
        raise ValueError("connect timeout must be between 1 and 120 seconds")
    if not 2.0 <= args.clock_sync_timeout <= 30.0:
        raise ValueError("clock sync timeout must be between 2 and 30 seconds")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    try:
        _validate_args(args)
        summary = asyncio.run(run_bench(args))
    except Exception as exc:
        print(f"R9 canonical IMU bench failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(asdict(summary), sort_keys=True, indent=2))
    return 0 if summary.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
