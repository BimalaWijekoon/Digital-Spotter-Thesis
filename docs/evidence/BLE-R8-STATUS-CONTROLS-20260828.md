# BLE R8 — bounded status and controls evidence

**Result:** PASS

**Completed:** 2026-08-28

**Environment:** real Raspberry Pi 4B, ESP32-C3, and MPU6500

**Mode:** plain BLE with `pair=false`; no bond, encryption, provisioning, cloud, or mock sensor

R8 added one read-only bounded status characteristic and four harmless research
controls while retaining the R7 recovery behavior and R6 20-byte real MPU6500
stream.

## Contract results

| Gate | Result |
|---|---|
| Exact R8 device info | PASS |
| Characteristic properties | PASS |
| Initial and final idle status | PASS |
| Streaming status and sample counter growth | PASS |
| Repeated start/stop | PASS, idempotent |
| Unknown command | PASS, `error:unknown_command` |
| Non-printable command | PASS, `error:invalid_text` |
| 49-byte command | PASS, `error:too_long` |
| Idle/stopped notification silence | PASS |
| Identify and buzzer commands during stream | PASS, no stream interruption |
| Clean disconnect and advertising recovery | PASS |

The concurrent stream result was:

```text
522 packets in 10.341136 seconds
50.478014 Hz notification rate
20 bytes per packet
12,218-27,815 us sensor intervals
0 sequence gaps
0 I2C errors
0 unexpected disconnects
```

## Failure-driven timing correction

The first candidate exposed paired `30.3/9.7 ms` timestamp intervals every five
seconds. ESP serial placed them at the existing long periodic `IMU_STATUS` print.
Suppressing that print only during streaming removed those pairs. A second run
isolated one `31.25/8.75 ms` pair to the `identify` NeoPixel transition. The
pinned NeoPixel driver performs synchronous RMT output.

The final narrow policy keeps the NeoPixel at one steady cyan value while the
stream is active and defers visual identify until stream stop. The buzzer remains
immediate and produced no outlier. The timestamp acceptance bounds were not
relaxed. Failed-run measurements and the pre-fix R8 binary remain in the R8
checkpoint.

## Final state and boundary

The Pi ended with Bluetooth active and powered, pairability and discovery off,
no paired/bonded/connected device, and no competing Bleak or `bluetoothctl`
process. R8 does not claim physical LED/buzzer observation, final cue policy,
bonding, application authentication, calibration, model semantics, or mounted
gym behavior. Those remain later stages.
