# BLE R6 — real MPU6500 stream evidence

**Result:** PASS
**Date:** 2026-08-27
**Environment:** real ESP32-C3, MPU6500, Raspberry Pi 4B, and owner-applied movement

R6 started from the passing R5 source and changed only the BLE stream values from
deterministic synthetic data to real MPU6500 raw counts. The 20-byte
little-endian layout, 50 Hz rate, UUIDs, GATT roles, sequence field, control echo,
and plain unpaired BLE transport remained unchanged.

## Hardware results

The final 30-second smoke received 1,502 packets. The two-minute stability run
received 6,002 packets. Both passed:

- every notification exactly 20 bytes;
- protocol version 1 and sensor-error flags clear;
- all six MPU6500 axes changed while the wearable was moved;
- no packet matched the retired synthetic formula;
- no all-zero acceleration substitution;
- continuous wrap-safe sequence and timestamp behavior;
- sensor capture rate approximately 50 Hz;
- no invalid lengths or unexpected disconnects.

The two-minute measurements were:

```text
samples=6002
notification_rate_hz=50.018092
sensor_capture_rate_hz=50.000027
sensor_interval_us=14966..25026
sequence_gaps=0
sensor_error_flags=0
invalid_packet_lengths=0
unexpected_disconnects=0
```

Observed two-minute raw ranges were:

| Axis | Minimum | Maximum | Unique values |
|---|---:|---:|---:|
| ax | -9552 | -8100 | 107 |
| ay | 13444 | 15264 | 117 |
| az | -1780 | -932 | 119 |
| gx | -183 | -67 | 74 |
| gy | -2 | 187 | 99 |
| gz | -134 | 222 | 148 |

## Timing defect found and corrected

The first R6 candidate exposed a real scheduling defect: two independent 20 ms
boundaries could cross by microseconds, causing the BLE side to skip a duplicate
sample and expose sequence gaps. The passing firmware aligns the first stream
boundary with the MPU schedule and rechecks the MPU immediately before notify.
The initial failed candidate and its logs remain in the R6 checkpoint.

One later 30-second run passed sequence continuity but failed the interval bound
before the validator printed interval diagnostics. The ESP firmware was not
changed afterward. Diagnostic-enabled 10-second, 30-second, and 120-second runs
all passed with measured 14.966-25.032 ms extrema and no outliers.

## Boundary

This proves real MPU6500 raw-count transport, not calibrated physical units,
wearable orientation, model compatibility, bonded security, automatic reconnect,
or mounted gym behavior. R7 will test reconnect and restart behavior without
adding bonding.
