"""Deterministic R9 sample, health, and latest-value core."""

from __future__ import annotations

import secrets
from collections import deque
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from digital_spotter.contracts import (
    ClockState,
    EventEnvelope,
    EventType,
    IMUSample,
    MonotonicNanoseconds,
    Quality,
    Source,
    new_event_id,
)
from digital_spotter.imu.clock import SensorClockMapper
from digital_spotter.imu.protocol import IMUProtocolError, IMUSequenceTracker
from digital_spotter.imu.r9_protocol import (
    R9DeviceInfo,
    R9Status,
    decode_stream_packet,
    parse_device_info,
    parse_status,
)


class R9ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    STREAMING = "streaming"
    DEGRADED = "degraded"
    STOPPING = "stopping"


@dataclass(frozen=True)
class R9AgentCounters:
    packets_received: int
    packets_emitted: int
    packets_duplicate: int
    packets_rejected: int
    sequence_gaps: int
    clock_resets: int
    notification_drops: int
    publisher_failures: int
    connection_failures: int
    reconnects: int
    clock_exchanges_accepted: int
    clock_exchanges_rejected: int
    clock_gate_drops: int


@dataclass(frozen=True)
class R9HealthSnapshot:
    state: R9ConnectionState
    connected: bool
    device_verified: bool
    streaming: bool
    sample_rate_hz: float | None
    latest_sequence: int | None
    latest_sample_age_ms: float | None
    i2c_errors: int
    samples_sent: int
    clock_state: ClockState
    clock_drift_ppm: float | None
    estimated_clock_error_ms: float
    clock_fit_points: int
    clock_exchange_age_ms: float | None
    counters: R9AgentCounters
    is_simulated: bool = False


class LatestSampleSlot:
    """One-value slot: consumers always see the newest accepted sample."""

    def __init__(self) -> None:
        self._event: EventEnvelope[IMUSample] | None = None
        self.version = 0

    def set(self, event: EventEnvelope[IMUSample]) -> None:
        self._event = event
        self.version += 1

    def get(self) -> EventEnvelope[IMUSample] | None:
        return self._event


class R9AgentCore:
    """Strict R9 core with no BlueZ, cloud, or application-security dependency."""

    is_real = True
    is_simulated = False
    persistence_allowed = True

    def __init__(
        self,
        *,
        device_id: str,
        initial_boot_id: int | None = None,
        rate_window_samples: int = 250,
        clock_mapper: SensorClockMapper | None = None,
    ) -> None:
        if not device_id or len(device_id) > 64:
            raise ValueError("device_id must contain 1-64 characters")
        if not 2 <= rate_window_samples <= 1000:
            raise ValueError("rate_window_samples must be between 2 and 1000")
        self.device_id = device_id
        self.session_id: UUID | None = None
        self.device_info: R9DeviceInfo | None = None
        self.status: R9Status | None = None
        self.latest = LatestSampleSlot()
        self._state = R9ConnectionState.DISCONNECTED
        self._connected = False
        self._streaming = False
        self._boot_id = (
            secrets.randbits(64) if initial_boot_id is None else initial_boot_id
        )
        if not 0 <= self._boot_id <= 0xFFFFFFFFFFFFFFFF:
            raise ValueError("initial_boot_id is outside u64")
        self._tracker = IMUSequenceTracker()
        self.clock_mapper = clock_mapper or SensorClockMapper()
        self._arrival_times_ns: deque[int] = deque(maxlen=rate_window_samples)
        self._received = 0
        self._emitted = 0
        self._duplicates = 0
        self._rejected = 0
        self._gaps = 0
        self._resets = 0
        self._notification_drops = 0
        self._publisher_failures = 0
        self._connection_failures = 0
        self._reconnects = 0
        self._clock_gate_drops = 0

    def set_session(self, session_id: UUID | None) -> None:
        self.session_id = session_id

    def mark_connecting(self) -> None:
        self._state = R9ConnectionState.CONNECTING

    def mark_connected(self) -> None:
        self._connected = True
        self._state = R9ConnectionState.READY

    def begin_stream(self) -> None:
        """Start a new R9 stream sequence epoch.

        The frozen R9 firmware deliberately restarts its raw u16 sequence at zero
        for every accepted ``stream:start`` command.  This is independent of an
        ESP boot, so retain the boot identity while resetting only raw sequence
        and delivery-rate tracking.
        """

        self._tracker = IMUSequenceTracker()
        self._arrival_times_ns.clear()

    def mark_streaming(self, enabled: bool) -> None:
        self._streaming = enabled
        if self._connected:
            self._state = (
                R9ConnectionState.STREAMING if enabled else R9ConnectionState.READY
            )

    def mark_stopping(self) -> None:
        self._state = R9ConnectionState.STOPPING

    def mark_disconnected(self) -> None:
        self._connected = False
        self._streaming = False
        self._state = R9ConnectionState.DISCONNECTED

    def note_notification_drop(self) -> None:
        self._notification_drops += 1

    def note_publisher_failure(self) -> None:
        self._publisher_failures += 1

    def note_connection_failure(self) -> None:
        self._connection_failures += 1

    def note_reconnect(self) -> None:
        self._reconnects += 1

    def note_clock_gate_drop(self) -> None:
        """Record a valid packet withheld until measurement time is trustworthy."""

        self._clock_gate_drops += 1

    def accept_device_info(self, payload: bytes) -> R9DeviceInfo:
        self.device_info = parse_device_info(payload)
        return self.device_info

    def accept_status(self, payload: bytes) -> R9Status:
        status = parse_status(payload)
        if self.status is not None and (
            status.uptime_ms < self.status.uptime_ms
            or status.samples_sent < self.status.samples_sent
        ):
            self._boot_id = (self._boot_id + 1) & 0xFFFFFFFFFFFFFFFF
            self._tracker = IMUSequenceTracker()
            self._arrival_times_ns.clear()
            self._resets += 1
        self.status = status
        if status.state == "error":
            self._state = R9ConnectionState.DEGRADED
        return status

    def accept_status_exchange(
        self,
        payload: bytes,
        *,
        t1_pi_ns: MonotonicNanoseconds,
        t4_pi_ns: MonotonicNanoseconds,
    ) -> R9Status:
        """Use one on-demand R9 status read as a bounded clock exchange.

        R9 generates ``uptime_ms`` inside its GATT read callback. The Pi records
        the request and response instants around that read. ESP ``millis()`` and
        packet ``micros()`` share the boot monotonic domain; converting the
        millisecond value to wrapping microseconds therefore supplies a coarse
        sensor timestamp with an explicit one-millisecond uncertainty.
        """

        status = self.accept_status(payload)
        sensor_time_us = (status.uptime_ms * 1000) & 0xFFFFFFFF
        self.clock_mapper.observe_exchange(
            boot_id=self._boot_id,
            t1_pi_ns=t1_pi_ns,
            sensor_receive_us=sensor_time_us,
            sensor_send_us=sensor_time_us,
            t4_pi_ns=t4_pi_ns,
            sensor_uncertainty_ns=1_000_000,
        )
        return status

    def accept_packet(
        self,
        payload: bytes,
        *,
        arrival_monotonic_ns: MonotonicNanoseconds,
    ) -> EventEnvelope[IMUSample] | None:
        self._received += 1
        try:
            if self.device_info is None or self.status is None:
                raise IMUProtocolError("R9 device info and status are required first")
            decoded = decode_stream_packet(payload)
            observation = self._tracker.observe(
                boot_id=self._boot_id,
                sequence=decoded.sequence,
            )
            if observation.duplicate:
                self._duplicates += 1
                return None
            self._gaps += observation.gap_count
            estimate = self.clock_mapper.map_sample(
                boot_id=self._boot_id,
                sensor_time_us=decoded.sensor_time_us,
                arrival_monotonic_ns=arrival_monotonic_ns,
            )
            self._arrival_times_ns.append(int(arrival_monotonic_ns))
            quality = Quality.IMU_DEGRADED
            event = EventEnvelope[IMUSample](
                event_type=EventType.IMU_SAMPLE,
                event_id=new_event_id(),
                source=Source.IMU,
                device_id=self.device_id,
                session_id=self.session_id,
                captured_monotonic_ns=estimate.captured_monotonic_ns,
                created_monotonic_ns=arrival_monotonic_ns,
                quality=quality,
                payload=IMUSample(
                    device_id=self.device_id,
                    boot_id=self._boot_id,
                    sequence=decoded.sequence,
                    sensor_time_us=decoded.sensor_time_us,
                    captured_monotonic_ns=estimate.captured_monotonic_ns,
                    arrival_monotonic_ns=arrival_monotonic_ns,
                    acceleration_m_s2=decoded.acceleration_m_s2,
                    angular_velocity_rad_s=decoded.angular_velocity_rad_s,
                    calibration_version=0,
                    quality=quality,
                    gap_count_since_previous=observation.gap_count,
                    estimated_clock_error_ns=estimate.estimated_error_ns,
                    clock_state=estimate.state,
                ),
            )
            self.latest.set(event)
            self._emitted += 1
            return event
        except IMUProtocolError:
            self._rejected += 1
            raise

    def _sample_rate_hz(self) -> float | None:
        if len(self._arrival_times_ns) < 2:
            return None
        elapsed_ns = self._arrival_times_ns[-1] - self._arrival_times_ns[0]
        if elapsed_ns <= 0:
            return None
        return (len(self._arrival_times_ns) - 1) * 1_000_000_000.0 / elapsed_ns

    def counters(self) -> R9AgentCounters:
        return R9AgentCounters(
            packets_received=self._received,
            packets_emitted=self._emitted,
            packets_duplicate=self._duplicates,
            packets_rejected=self._rejected,
            sequence_gaps=self._gaps,
            clock_resets=self._resets,
            notification_drops=self._notification_drops,
            publisher_failures=self._publisher_failures,
            connection_failures=self._connection_failures,
            reconnects=self._reconnects,
            clock_exchanges_accepted=self.clock_mapper.accepted_exchange_count,
            clock_exchanges_rejected=self.clock_mapper.rejected_exchange_count,
            clock_gate_drops=self._clock_gate_drops,
        )

    def health(
        self,
        *,
        now_monotonic_ns: int,
        stale_after_ms: float = 250.0,
    ) -> R9HealthSnapshot:
        if stale_after_ms <= 0:
            raise ValueError("stale_after_ms must be positive")
        latest = self.latest.get()
        age_ms = None
        if latest is not None:
            age_ms = max(
                0.0,
                (now_monotonic_ns - int(latest.created_monotonic_ns)) / 1_000_000.0,
            )
        state = self._state
        if self._connected and self._streaming and (
            latest is None or age_ms is None or age_ms > stale_after_ms
        ):
            state = R9ConnectionState.DEGRADED
        if self.status is not None and self.status.i2c_errors:
            state = R9ConnectionState.DEGRADED
        clock_state = self.clock_mapper.state_at(
            MonotonicNanoseconds(now_monotonic_ns)
        )
        latest_exchange = next(
            (
                diagnostic
                for diagnostic in reversed(self.clock_mapper.exchange_diagnostics)
                if diagnostic.accepted
            ),
            None,
        )
        exchange_age_ms = None
        if latest_exchange is not None:
            exchange_age_ms = max(
                0.0,
                (now_monotonic_ns - latest_exchange.pi_mid_ns) / 1_000_000.0,
            )
        return R9HealthSnapshot(
            state=state,
            connected=self._connected,
            device_verified=self.device_info is not None,
            streaming=self._streaming,
            sample_rate_hz=self._sample_rate_hz(),
            latest_sequence=None if latest is None else latest.payload.sequence,
            latest_sample_age_ms=age_ms,
            i2c_errors=0 if self.status is None else self.status.i2c_errors,
            samples_sent=0 if self.status is None else self.status.samples_sent,
            clock_state=clock_state,
            clock_drift_ppm=self.clock_mapper.drift_ppm,
            estimated_clock_error_ms=(
                self.clock_mapper.estimated_error_ns / 1_000_000.0
            ),
            clock_fit_points=self.clock_mapper.fit_point_count,
            clock_exchange_age_ms=exchange_age_ms,
            counters=self.counters(),
        )
