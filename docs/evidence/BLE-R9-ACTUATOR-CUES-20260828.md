# BLE R9 actuator-cue evidence — 2026-08-28

## Scope

R9 changed only the GPIO 8 NeoPixel / GPIO 10 buzzer execution policy and the
matching research validator. It retained the frozen R8 BLE name/address, UUIDs,
plain unpaired mode, status schema, explicit stream controls, 20-byte packet, real
MPU6500 source, and provisional 50 Hz schedule. R10 bonding and later product
security were not started.

## Frozen input and output

- R8 source SHA256: `45a89f15fa595630b479aff61e754cdc1ae091bf5649c11ca2a3dea4875288da`
- R9 source SHA256: `5cf7f44400954611d307093503e710840576a6d5f5fff169e25f5753fae2283b`
- R9 Pi validator SHA256: `6acdac61ae9e2779b691cdad7cb14916f4d19b9e03936ad66600f783ea1c1f7f`
- R9 application binary size: `666560` bytes
- R9 application binary SHA256: `4432368b23dd2cf04f1fc528a1b2fadd769015ddd1834cd473f25f06f2697ea3`
- Application offset: `0x10000`
- Checkpoint: `firmware/esp32_c3_research/checkpoints/r9/pass/`

The build used Arduino CLI 1.5.1 commit `01f3d4f2b`, Arduino-ESP32 3.3.10,
Adafruit NeoPixel 1.15.5, and FQBN `esp32:esp32:esp32c3`. Compilation reported
666,403 bytes of program storage and 19,628 bytes of global RAM. Flash verification
passed. No full-chip erase, NVS erase, pairing, bonding, or BlueZ-state deletion
was performed.

## Cue contract

| State/test | GPIO 8 cue |
|---|---|
| boot | white for 800 ms |
| advertising | blue breathing |
| connected idle | solid green |
| streaming | steady cyan |
| disconnected | orange for 500 ms, then advertising |
| sensor error | solid red |
| identify | white for 900 ms, deferred until stream stop |

GPIO 10 `buzzer:test` is one non-blocking 2,500 Hz, 120 ms beep. `cue:test`
executes the six state colors for 900 ms each while connected and idle, and returns
`error:busy_streaming` during a stream. `DS_ENABLE_ACTUATOR_CUES=0` is the R9
rollback switch. No model-derived feedback was enabled.

## Failure-driven correction

The first candidate preserved BLE and delivered over 1,500 packets with zero
sequence gaps, I2C errors, or disconnects, but failed the unchanged timing bound.
A diagnostic rerun reproduced a paired `31,629 us` / `8,354 us` interval around
the verbose existing identify write/read logging. Its measurements are retained
here; the failed candidate binaries/source were removed in the owner-approved
2026-08-28 workspace cleanup after the corrected R9 checkpoint was frozen.

The focused correction defers nonessential GATT and actuator serial messages while
the real-time stream is active and reports their count after stop. It does not
change command responses, sensor scheduling, BLE properties, or packet data.

## Corrected automated test

Command on the Pi:

```text
cd /home/pibimalawijekoon/ble-test
.venv/bin/python pi_ble_r9_actuator_test.py --duration 30
```

Result:

```text
duration_seconds=30.001075
samples=1499
notification_rate_hz=49.964876
sequence_gaps=0
sensor_interval_min_us=14998
sensor_interval_max_us=24994
i2c_errors=0
samples_sent=1512
unexpected_disconnects=0
TEST RESULT: PASS
```

During the measured stream, `cue:test` was correctly rejected, the manual buzzer
ran, identify was accepted and deferred, all packets were 20 bytes with protocol
1/flags 0, and the link remained connected. The idle six-color cue test then
completed without a disconnect.

## Physical observation

The owner tapped RESET/EN and confirmed the actual white boot cue followed by blue
advertising. The automated cue demo was then run twice. The owner confirmed the
sequence exactly as described and heard the short buzzer: green connected; white,
blue, green, cyan, orange, red; steady cyan streaming; one beep; green idle;
orange disconnect; blue advertising.

After the owner's reset, the final serial status still reported exact
`WHO_AM_I=0x70`, `ready=1`, zero terminal/consecutive errors, and one recovered
I2C retry/bus failure. The measured acceptance stream itself had zero I2C errors.
The Pi ended with Bluetooth active/powered, discovery off, no connected/paired/
bonded DS device, `throttled=0x0`, and temperature 53.5 C.

## Gate result

R9 is PASS and frozen. Hardware was real: Raspberry Pi 4B, ESP32-C3, GPIO 8
NeoPixel, GPIO 10 buzzer, and MPU6500 at `0x68`. No mocks or replay data were used.
R10 has not started.
