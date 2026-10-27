"""Deterministic core of the Pi BLE agent, independent of BlueZ callbacks."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import msgpack

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
from digital_spotter.imu.protocol import (
    BoundedIMUBuffer,
    DeviceInfo,
    IMUFlags,
    IMUProtocolError,
    IMUSequenceTracker,
    WearableStatus,
    decode_imu_packet,
    encode_imu_packet,
    parse_device_info,
    parse_wearable_status,
)
from digital_spotter.imu.clock import SensorClockMapper


@dataclass(frozen=True)
class IMUAgentCounters:
    packets_received: int
    packets_emitted: int
    packets_duplicate: int
    packets_rejected: int
    packets_evicted: int
    sequence_gaps: int
    clock_resets: int


class IMUAgentCore:
    """Parse one provisioned wearable without implying clock synchronization."""

    is_real = True
    is_simulated = False
    persistence_allowed = True

    def __init__(
        self,
        *,
        expected_device_id: str,
        max_buffer_samples: int = 250,
        clock_mapper: SensorClockMapper | None = None,
    ):
        if not expected_device_id or len(expected_device_id) > 64:
            raise ValueError("expected_device_id must contain 1-64 characters")
        self.expected_device_id = expected_device_id
        self.buffer = BoundedIMUBuffer(max_buffer_samples)
        self.status: WearableStatus | None = None
        self.device_info: DeviceInfo | None = None
        self.session_id: UUID | None = None
        self._tracker = IMUSequenceTracker()
        self.clock_mapper = clock_mapper
        self._received = 0
        self._emitted = 0
        self._duplicates = 0
        self._rejected = 0
        self._gaps = 0
        self._resets = 0

    def set_session(self, session_id: UUID | None) -> None:
        self.session_id = session_id

    def accept_device_info(self, encoded: bytes) -> DeviceInfo:
        info = parse_device_info(encoded)
        if info.device_id != self.expected_device_id:
            raise IMUProtocolError("wearable device identity does not match provisioning")
        self.device_info = info
        return info

    def accept_status(self, encoded: bytes) -> WearableStatus:
        status = parse_wearable_status(encoded)
        if status.device_id != self.expected_device_id:
            raise IMUProtocolError("wearable status identity does not match provisioning")
        if self.device_info is not None and (
            status.scale_profile_version != self.device_info.scale_profile_version
            or status.sample_rate_hz != self.device_info.sample_rate_hz
        ):
            raise IMUProtocolError("wearable status contradicts device info")
        self.status = status
        return status

    def accept_packet(
        self,
        packet: bytes,
        *,
        arrival_monotonic_ns: MonotonicNanoseconds,
    ) -> EventEnvelope[IMUSample] | None:
        self._received += 1
        try:
            if self.status is None or self.device_info is None:
                raise IMUProtocolError("status and device info are required before samples")
            decoded = decode_imu_packet(
                packet,
                scale_profile_version=self.status.scale_profile_version,
            )
            observation = self._tracker.observe(
                boot_id=self.status.boot_id,
                sequence=decoded.sequence,
            )
            if observation.duplicate:
                self._duplicates += 1
                return None
            self._gaps += observation.gap_count
            self._resets += int(observation.clock_reset)
            self.buffer.append(decoded)

            if self.clock_mapper is None:
                captured_monotonic_ns = arrival_monotonic_ns
                estimated_clock_error_ns = 50_000_000
                clock_state = (
                    ClockState.RESET if observation.clock_reset else ClockState.ACQUIRING
                )
            else:
                estimate = self.clock_mapper.map_sample(
                    boot_id=self.status.boot_id,
                    sensor_time_us=decoded.sensor_time_us,
                    arrival_monotonic_ns=arrival_monotonic_ns,
                )
                captured_monotonic_ns = estimate.captured_monotonic_ns
                estimated_clock_error_ns = estimate.estimated_error_ns
                clock_state = estimate.state
            quality = (
                Quality.GOOD
                if clock_state is ClockState.SYNCHRONIZED
                else Quality.UNSYNCHRONIZED
            )
            if decoded.flags & IMUFlags.SENSOR_ERROR:
                quality = Quality.UNAVAILABLE
            elif decoded.flags & IMUFlags.SATURATED or observation.gap_count:
                quality = Quality.IMU_DEGRADED
            # Absence of calibration is intentionally degraded even though the
            # M2-04 clock mapper is also still acquiring.
            elif not decoded.flags & IMUFlags.CALIBRATED:
                quality = Quality.IMU_DEGRADED

            payload = IMUSample(
                device_id=self.expected_device_id,
                boot_id=self.status.boot_id,
                sequence=decoded.sequence,
                sensor_time_us=decoded.sensor_time_us,
                captured_monotonic_ns=captured_monotonic_ns,
                arrival_monotonic_ns=arrival_monotonic_ns,
                acceleration_m_s2=decoded.acceleration_m_s2,
                angular_velocity_rad_s=decoded.angular_velocity_rad_s,
                calibration_version=self.status.calibration_version,
                quality=quality,
                gap_count_since_previous=observation.gap_count,
                estimated_clock_error_ns=estimated_clock_error_ns,
                clock_state=clock_state,
            )
            envelope = EventEnvelope[IMUSample](
                event_type=EventType.IMU_SAMPLE,
                event_id=new_event_id(),
                source=Source.IMU,
                device_id=self.expected_device_id,
                session_id=self.session_id,
                captured_monotonic_ns=captured_monotonic_ns,
                created_monotonic_ns=arrival_monotonic_ns,
                quality=quality,
                payload=payload,
            )
            self._emitted += 1
            return envelope
        except IMUProtocolError:
            self._rejected += 1
            raise

    def counters(self) -> IMUAgentCounters:
        return IMUAgentCounters(
            packets_received=self._received,
            packets_emitted=self._emitted,
            packets_duplicate=self._duplicates,
            packets_rejected=self._rejected,
            packets_evicted=self.buffer.evicted_count,
            sequence_gaps=self._gaps,
            clock_resets=self._resets,
        )


class FakeWearable:
    """Synthetic packet source that can never be mistaken for BLE hardware."""

    is_real = False
    is_simulated = True
    persistence_allowed = False

    def __init__(self, *, device_id: str = "imu-fake-001", boot_id: int = 1):
        self.device_id = device_id
        self.boot_id = boot_id

    def device_info(self) -> bytes:
        return msgpack.packb(
            {
                "protocol_version": 1,
                "device_id": self.device_id,
                "firmware_version": "0.0.0-fake",
                "hardware_revision": "synthetic",
                "imu_model": "MPU6500",
                "service_uuid": "fba6b009-755a-53f9-9743-4d1850269448",
                "scale_profile_version": 1,
                "acceleration_lsb_per_g": 16384,
                "gyroscope_lsb_per_degree_s": 131,
                "sample_rate_hz": 50,
            },
            use_bin_type=True,
        )

    def status(self, *, state: str = "streaming") -> bytes:
        return msgpack.packb(
            {
                "protocol_version": 1,
                "device_id": self.device_id,
                "boot_id": self.boot_id,
                "state": state,
                "firmware_version": "0.0.0-fake",
                "hardware_revision": "synthetic",
                "imu_model": "MPU6500",
                "scale_profile_version": 1,
                "calibration_version": 1,
                "battery_mv": 4000,
                "battery_percent": 80,
                "sample_rate_hz": 50,
                "samples_sent": 0,
                "sensor_errors": 0,
                "sensor_retries": 0,
                "last_error_code": None,
                "heap_free_bytes": 200_000,
                "heap_minimum_free_bytes": 190_000,
                "uptime_ms": 1,
            },
            use_bin_type=True,
        )

    def packet(
        self,
        *,
        sequence: int,
        sensor_time_us: int,
        flags: IMUFlags = IMUFlags.CALIBRATED,
    ) -> bytes:
        return encode_imu_packet(
            flags=flags,
            sequence=sequence,
            sensor_time_us=sensor_time_us,
            acceleration_raw=(0, 16384, 0),
            angular_velocity_raw=(0, 0, 0),
        )
