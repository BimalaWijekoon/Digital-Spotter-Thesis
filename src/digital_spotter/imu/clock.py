"""Deterministic ESP u32-microsecond to Pi monotonic-nanosecond clock mapping."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from digital_spotter.contracts import ClockState, MonotonicNanoseconds
from digital_spotter.imu.protocol import IMUProtocolError


U32_MODULUS = 1 << 32


@dataclass(frozen=True)
class ClockEstimate:
    captured_monotonic_ns: MonotonicNanoseconds
    estimated_error_ns: int
    state: ClockState
    drift_ppm: float | None


@dataclass(frozen=True)
class ClockExchangeDiagnostic:
    """One bounded, non-secret observation of the clock exchange path."""

    sensor_mid_us: float
    pi_mid_ns: float
    processing_ns: int
    round_trip_ns: int
    sensor_uncertainty_ns: int
    accepted: bool
    estimated_error_ns: int
    state: ClockState
    drift_ppm: float | None


class SensorClockMapper:
    def __init__(
        self,
        *,
        min_exchanges: int = 5,
        max_exchanges: int = 20,
        max_rtt_ns: int = 50_000_000,
        synchronized_error_ns: int = 20_000_000,
        max_abs_drift_ppm: float = 500.0,
        low_delay_slack_ns: int = 0,
        min_drift_span_us: int = 5_000_000,
        max_exchange_age_ns: int = 5_000_000_000,
    ):
        if not 3 <= min_exchanges <= max_exchanges <= 100:
            raise ValueError("clock exchange window is invalid")
        if low_delay_slack_ns < 0:
            raise ValueError("low-delay slack must not be negative")
        if min_drift_span_us <= 0:
            raise ValueError("minimum drift span must be positive")
        if max_exchange_age_ns <= 0:
            raise ValueError("maximum exchange age must be positive")
        self.min_exchanges = min_exchanges
        self.max_rtt_ns = max_rtt_ns
        self.synchronized_error_ns = synchronized_error_ns
        self.max_abs_drift_ppm = max_abs_drift_ppm
        self.low_delay_slack_ns = low_delay_slack_ns
        self.min_drift_span_us = min_drift_span_us
        self.max_exchange_age_ns = max_exchange_age_ns
        self._points: deque[tuple[float, float, int, int]] = deque(
            maxlen=max_exchanges
        )
        self._exchange_diagnostics: deque[ClockExchangeDiagnostic] = deque(maxlen=100)
        self._boot_id: int | None = None
        self._latest_sensor_us: int | None = None
        self._slope: float | None = None
        self._intercept: float | None = None
        self._estimated_error_ns = max_rtt_ns
        self._state = ClockState.ACQUIRING
        self._just_reset = False
        self._fit_point_count = 0
        self._fit_rtt_max_ns: int | None = None
        self._drift_observed = False
        self._causal_cap_samples = 0
        self._max_future_projection_ns = 0
        self._latest_accepted_pi_mid_ns: int | None = None
        self._accepted_exchanges = 0
        self._rejected_exchanges = 0
        self._last_capture_ns: int | None = None
        self._monotonic_correction_samples = 0
        self._max_monotonic_correction_ns = 0

    @property
    def state(self) -> ClockState:
        return self._state

    @property
    def drift_ppm(self) -> float | None:
        if self._slope is None:
            return None
        return (self._slope / 1000.0 - 1.0) * 1_000_000.0

    @property
    def estimated_error_ns(self) -> int:
        return self._estimated_error_ns

    @property
    def exchange_diagnostics(self) -> tuple[ClockExchangeDiagnostic, ...]:
        return tuple(self._exchange_diagnostics)

    @property
    def fit_point_count(self) -> int:
        return self._fit_point_count

    @property
    def fit_rtt_max_ns(self) -> int | None:
        return self._fit_rtt_max_ns

    @property
    def drift_observed(self) -> bool:
        return self._drift_observed

    @property
    def causal_cap_samples(self) -> int:
        return self._causal_cap_samples

    @property
    def max_future_projection_ns(self) -> int:
        return self._max_future_projection_ns

    @property
    def accepted_exchange_count(self) -> int:
        return self._accepted_exchanges

    @property
    def rejected_exchange_count(self) -> int:
        return self._rejected_exchanges

    @property
    def monotonic_correction_samples(self) -> int:
        return self._monotonic_correction_samples

    @property
    def max_monotonic_correction_ns(self) -> int:
        return self._max_monotonic_correction_ns

    def state_at(self, now_monotonic_ns: MonotonicNanoseconds) -> ClockState:
        """Return clock quality at a caller-supplied monotonic instant."""

        if self._latest_accepted_pi_mid_ns is None:
            return self._state
        if int(now_monotonic_ns) < self._latest_accepted_pi_mid_ns:
            return ClockState.DEGRADED
        if (
            int(now_monotonic_ns) - self._latest_accepted_pi_mid_ns
            > self.max_exchange_age_ns
        ):
            return ClockState.DEGRADED
        return self._state

    def _set_boot(self, boot_id: int) -> bool:
        if not 0 <= boot_id <= 0xFFFFFFFFFFFFFFFF:
            raise IMUProtocolError("boot_id is outside u64")
        if self._boot_id is None:
            self._boot_id = boot_id
            return False
        if self._boot_id == boot_id:
            return False
        self._boot_id = boot_id
        self._latest_sensor_us = None
        self._points.clear()
        self._exchange_diagnostics.clear()
        self._slope = None
        self._intercept = None
        self._estimated_error_ns = self.max_rtt_ns
        self._state = ClockState.RESET
        self._just_reset = True
        self._fit_point_count = 0
        self._fit_rtt_max_ns = None
        self._drift_observed = False
        self._causal_cap_samples = 0
        self._max_future_projection_ns = 0
        self._latest_accepted_pi_mid_ns = None
        self._accepted_exchanges = 0
        self._rejected_exchanges = 0
        self._last_capture_ns = None
        self._monotonic_correction_samples = 0
        self._max_monotonic_correction_ns = 0
        return True

    def _record_exchange(
        self,
        *,
        sensor_mid_us: float,
        pi_mid_ns: float,
        processing_ns: int,
        round_trip_ns: int,
        sensor_uncertainty_ns: int,
        accepted: bool,
    ) -> None:
        if accepted:
            self._accepted_exchanges += 1
        else:
            self._rejected_exchanges += 1
        self._exchange_diagnostics.append(
            ClockExchangeDiagnostic(
                sensor_mid_us=sensor_mid_us,
                pi_mid_ns=pi_mid_ns,
                processing_ns=processing_ns,
                round_trip_ns=round_trip_ns,
                sensor_uncertainty_ns=sensor_uncertainty_ns,
                accepted=accepted,
                estimated_error_ns=self._estimated_error_ns,
                state=self._state,
                drift_ppm=self.drift_ppm,
            )
        )

    def _unwrap_near(self, raw_us: int) -> int:
        if not 0 <= raw_us <= 0xFFFFFFFF:
            raise IMUProtocolError("sensor_time_us is outside u32")
        if self._latest_sensor_us is None:
            unwrapped = raw_us
        else:
            cycles = round((self._latest_sensor_us - raw_us) / U32_MODULUS)
            candidates = [raw_us + (cycles + offset) * U32_MODULUS for offset in (-1, 0, 1)]
            unwrapped = min(candidates, key=lambda value: abs(value - self._latest_sensor_us))
            if unwrapped < 0:
                raise IMUProtocolError("sensor counter unwrap produced negative time")
        if self._latest_sensor_us is None or unwrapped > self._latest_sensor_us:
            self._latest_sensor_us = unwrapped
        return unwrapped

    def observe_exchange(
        self,
        *,
        boot_id: int,
        t1_pi_ns: MonotonicNanoseconds,
        sensor_receive_us: int,
        sensor_send_us: int,
        t4_pi_ns: MonotonicNanoseconds,
        sensor_uncertainty_ns: int = 0,
    ) -> bool:
        reset = self._set_boot(boot_id)
        if not 0 <= sensor_uncertainty_ns <= 1_000_000_000:
            raise IMUProtocolError("sensor timestamp uncertainty is outside bounds")
        if t4_pi_ns < t1_pi_ns:
            raise IMUProtocolError("time-sync response precedes request")
        receive = self._unwrap_near(sensor_receive_us)
        send = self._unwrap_near(sensor_send_us)
        if send < receive:
            send += U32_MODULUS
        processing_ns = (send - receive) * 1000
        round_trip_ns = int(t4_pi_ns - t1_pi_ns) - processing_ns
        sensor_mid_us = (receive + send) / 2.0
        pi_mid_ns = (int(t1_pi_ns) + int(t4_pi_ns)) / 2.0
        if round_trip_ns < 0 or round_trip_ns > self.max_rtt_ns:
            self._record_exchange(
                sensor_mid_us=sensor_mid_us,
                pi_mid_ns=pi_mid_ns,
                processing_ns=processing_ns,
                round_trip_ns=round_trip_ns,
                sensor_uncertainty_ns=sensor_uncertainty_ns,
                accepted=False,
            )
            return False
        self._points.append(
            (sensor_mid_us, pi_mid_ns, round_trip_ns, sensor_uncertainty_ns)
        )
        self._latest_accepted_pi_mid_ns = round(pi_mid_ns)
        self._fit()
        self._record_exchange(
            sensor_mid_us=sensor_mid_us,
            pi_mid_ns=pi_mid_ns,
            processing_ns=processing_ns,
            round_trip_ns=round_trip_ns,
            sensor_uncertainty_ns=sensor_uncertainty_ns,
            accepted=True,
        )
        if reset:
            self._just_reset = True
        return True

    def _fit(self) -> None:
        if len(self._points) < 2:
            self._state = ClockState.ACQUIRING
            return

        # BLE scheduling can add tens of milliseconds of variable delay. Use the
        # lowest-delay observations as the NTP-style clock filter; higher-delay
        # points remain visible in diagnostics but must not pull the clock model.
        ordered_by_rtt = sorted(self._points, key=lambda point: point[2])
        minimum_fit_count = min(
            len(ordered_by_rtt),
            max(self.min_exchanges, math.ceil(len(ordered_by_rtt) / 2)),
        )
        median_rtt = ordered_by_rtt[math.ceil(len(ordered_by_rtt) / 2) - 1][2]
        cutoff_rtt = median_rtt + self.low_delay_slack_ns
        fit_points = [point for point in ordered_by_rtt if point[2] <= cutoff_rtt]
        if len(fit_points) < minimum_fit_count:
            fit_points = ordered_by_rtt[:minimum_fit_count]
        self._fit_point_count = len(fit_points)
        self._fit_rtt_max_ns = max(point[2] for point in fit_points)

        sensor_span_us = max(point[0] for point in fit_points) - min(
            point[0] for point in fit_points
        )
        if sensor_span_us < self.min_drift_span_us:
            # A short exchange burst cannot distinguish oscillator drift from
            # millisecond BLE path asymmetry. Bootstrap with the protocol's
            # microsecond rate and robustly estimate only the offset.
            self._slope = 1000.0
            offsets = sorted(point[1] - self._slope * point[0] for point in fit_points)
            self._intercept = offsets[(len(offsets) - 1) // 2]
            self._drift_observed = False
        else:
            mean_sensor = sum(point[0] for point in fit_points) / len(fit_points)
            mean_pi = sum(point[1] for point in fit_points) / len(fit_points)
            variance = sum((point[0] - mean_sensor) ** 2 for point in fit_points)
            if variance <= 0:
                self._state = ClockState.ACQUIRING
                return
            covariance = sum(
                (point[0] - mean_sensor) * (point[1] - mean_pi)
                for point in fit_points
            )
            self._slope = covariance / variance
            self._intercept = mean_pi - self._slope * mean_sensor
            self._drift_observed = True

        residuals = sorted(
            abs((self._intercept + self._slope * point[0]) - point[1])
            + point[2] / 2
            + point[3]
            for point in fit_points
        )
        p95_index = max(0, math.ceil(0.95 * len(residuals)) - 1)
        self._estimated_error_ns = max(1, math.ceil(residuals[p95_index]))
        if len(self._points) < self.min_exchanges:
            self._state = ClockState.ACQUIRING
        elif (
            self._estimated_error_ns <= self.synchronized_error_ns
            and abs(self.drift_ppm or 0.0) <= self.max_abs_drift_ppm
        ):
            self._state = ClockState.SYNCHRONIZED
            self._just_reset = False
        else:
            self._state = ClockState.DEGRADED

    def map_sample(
        self,
        *,
        boot_id: int,
        sensor_time_us: int,
        arrival_monotonic_ns: MonotonicNanoseconds,
    ) -> ClockEstimate:
        reset = self._set_boot(boot_id)
        sensor_unwrapped = self._unwrap_near(sensor_time_us)
        report_reset = reset or self._just_reset
        if report_reset:
            state = ClockState.RESET
            self._just_reset = False
            if self._state is ClockState.RESET:
                self._state = ClockState.ACQUIRING
        else:
            state = self.state_at(arrival_monotonic_ns)
        if self._slope is None or self._intercept is None:
            fallback_capture = int(arrival_monotonic_ns)
            if (
                self._last_capture_ns is not None
                and fallback_capture < self._last_capture_ns
            ):
                raise IMUProtocolError("arrival time moved backward during acquisition")
            self._last_capture_ns = fallback_capture
            return ClockEstimate(
                captured_monotonic_ns=MonotonicNanoseconds(fallback_capture),
                estimated_error_ns=self.max_rtt_ns,
                state=state,
                drift_ppm=self.drift_ppm,
            )
        mapped = round(self._intercept + self._slope * sensor_unwrapped)
        if mapped < 0:
            raise IMUProtocolError("mapped sensor time is negative")
        future_error = max(0, mapped - int(arrival_monotonic_ns))
        estimated_error = max(self._estimated_error_ns, future_error)
        if state is ClockState.DEGRADED:
            estimated_error = max(
                estimated_error,
                self.synchronized_error_ns + 1,
            )
        if future_error:
            self._causal_cap_samples += 1
            self._max_future_projection_ns = max(
                self._max_future_projection_ns,
                future_error,
            )
        if future_error > self.synchronized_error_ns:
            state = ClockState.DEGRADED
        # Capture cannot causally follow receipt. A small positive projection is
        # possible with an asymmetric BLE exchange; cap it at arrival while the
        # full projection error remains explicit in estimated_error_ns/state.
        causal_mapped = min(mapped, int(arrival_monotonic_ns))
        if self._last_capture_ns is not None and causal_mapped < self._last_capture_ns:
            correction = self._last_capture_ns - causal_mapped
            causal_mapped = self._last_capture_ns
            estimated_error = max(estimated_error, correction)
            self._monotonic_correction_samples += 1
            self._max_monotonic_correction_ns = max(
                self._max_monotonic_correction_ns,
                correction,
            )
            if correction > self.synchronized_error_ns:
                state = ClockState.DEGRADED
        self._last_capture_ns = causal_mapped
        return ClockEstimate(
            captured_monotonic_ns=MonotonicNanoseconds(causal_mapped),
            estimated_error_ns=estimated_error,
            state=state,
            drift_ppm=self.drift_ppm,
        )
