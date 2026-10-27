# Assembled wearable PCB integration — M2-07

Date: 2026-10-19. Status: implementation in progress. PCB firmware source and
Pi identity compatibility are adapted, firmware compile and 17 focused host
checks pass. Application upload, MPU6500/PWM/BLE startup and the external-power
30-second IMU stream pass (1,499 packets, 49.965309 Hz, zero gaps/errors/
disconnects). Dashboard graph data and existing camera-only playback are back.
Physical cue replay and mounted pose/rep/model checks are still pending. The
pose-enabled startup timeout was resolved on 2026-10-20 with a pinned isolated
pose environment; one short real combined run delivered 94 pose events (all
person missing), no processing errors and a gap-free IMU window. Current evidence:
[M2-07 report](evidence/M2-07-PCB-INTEGRATION-20261019.md).

Restore the original R9 BLE/50 Hz application on the assembled PCB, replace its
NeoPixel output with the external RGB module, adapt its buzzer drive, and bring
the existing Pi camera/IMU/UI path back into operation. This is the controlled
research profile in ADR-019.

## Evidence inspected at the initial planning pass

- The working source and the frozen R9 checkpoint source still have identical
  SHA256 `5cf7f44400954611d307093503e710840576a6d5f5fff169e25f5753fae2283b`.
  Source: `firmware/esp32_c3_research/esp32_c3_research.ino`.
- The assembled-PCB diagnostics verified MPU6500 identity and motion. The owner
  confirmed the external RGB loop and buzzer with external power on 2026-10-17.
  Sources: `firmware/imu_pcb_bringup/README.md` and its `IMU_Bringup/pin_config.h`.
- The last verified flashed application is the actuator-only power test; it
  has no BLE or IMU acquisition. Its retained binary hash still matches
  `4524064988b974514950327478b8eb67b823251dabbc0552143456c89c5f3efc`.
  The ESP flash was not read or changed during this planning pass.
- Live Pi SSH succeeded. Bluetooth is active, powered, and not discovering;
  `throttled=0x0`, temperature 45.2 C. Port 8766 is not listening and the
  inspected project camera/BLE/UI runners are stopped after boot.
- Windows lists COM7. No serial port was opened during planning; chip/port
  identity must be checked again at upload time.
- The deployed Pi copy at `~/digital-spotter-research-status-20261003/` still
  requires the exact R9 device-info string. Source:
  `src/digital_spotter/imu/r9_protocol.py` locally and on the Pi.

## Hardware changes

| Function | Original R9 | Assembled PCB |
|---|---|---|
| MPU6500 SDA/SCL | GPIO5 / GPIO6 | GPIO18 / GPIO19 |
| RGB | GPIO8 WS2812/NeoPixel | Red GPIO1, green GPIO0, blue GPIO3; active HIGH |
| Buzzer | GPIO10, `tone()` | GPIO10 into Q7 driver; timed HIGH/LOW for active buzzer |
| IMU profile | 0x68, identity 0x70, ±2 g, ±250 °/s, 50 Hz | Retain these settings |

GPIO18/19 are occupied by I2C. Upload and serial monitoring use the existing
USB-UART bridge with native USB CDC disabled. The temporary diagnostic's 20 Hz
rate is not the application rate.

## Execution steps

### 1. Preserve the starting point and update the application

Keep the frozen R9 checkpoint untouched. Save the current source/configuration
and retain the tested PCB diagnostic binary before editing. Work in the original
`firmware/esp32_c3_research/` application with a small explicit board pin header.

Change SDA/SCL to GPIO18/19. Replace NeoPixel output with the Arduino core's
hardware PWM on the three RGB pins so white, cyan, orange, and the existing
single colours remain available. Set outputs LOW at initialization. Keep the
existing state meanings and steady streaming colour; output changes occur on
state transitions rather than for every packet.

Replace `tone()` with the tested active-buzzer HIGH/LOW drive and a bounded
non-blocking timer. Use a 500 ms manual test pulse, matching the audible PCB
diagnostic. The automatic test loop must not run in this application. Preserve
the existing stream controls and sensor-error handling. Correct the stale R4
synthetic-data startup message while retaining the real raw-sample pipeline.

### 2. Keep firmware and Pi compatibility explicit

Identify the new firmware as `0.9.1-pcb1`. Retain protocol version 1, device name,
address expectations, UUIDs, 20-byte packet layout, sequence/timestamps, 50 Hz,
and sensor scale profile. No pairing or provisioning workflow is added.

Update `r9_protocol.py` and the standalone validator to accept an explicit
allow-list of the frozen R9 and new PCB device-info values. Report the actual
accepted firmware version. Continue rejecting unknown versions and malformed
contracts. Preserve the research device ID so existing Pi configuration and
session identity remain compatible.

Run only the directly affected firmware build and host identity/agent checks.
Preserve a copy of the installed Pi files before deploying the matched update.
Do not change Pi networking, Tailscale, Bluetooth-wide configuration, models,
or databases for this hardware adaptation.

### 3. Build, upload, and verify sensor startup

Use Arduino-ESP32 3.3.10 and FQBN `esp32:esp32:esp32c3`. Record the application
hash and verified partition offset. With the converter physically unplugged,
JP1 cap OFF, and ESP USB power only, flash the application partition.

Inspect one startup log: correct PCB pins, MPU6500 identity 0x70 at 0x68,
50 Hz configuration, BLE advertising, and no reset loop. Read back the relevant
sensor configuration to confirm the decoder's ±2 g/±250 °/s profile. No flash
erase, NVS erase, bond removal, or new key is needed.

For the externally powered observation, unplug USB first, then connect the
existing converter and switch on. This is the physical handoff needed to verify
the actual buzzer supply. Never combine the converter and ESP USB power.

### 4. Check the changed wearable path once

Run one approximately 30-second real BLE stream on the Pi with one central
client. Check 20-byte packets, approximately 50 Hz, sequence continuity,
monotonic sensor timestamps, changing real axes, and I2C/disconnect counters.
Use a short stationary interval and an owner-cued tilt/rotation interval; check
that values settle afterward. The previous motion test did not finish that
settling observation because its USB connection dropped.

Exercise the state-colour sequence and one buzzer pulse; include a pulse during
streaming to check that the changed driver does not interrupt sample delivery.
Use one normal restart/reconnect after the power handoff to check integration
with the existing recovery path. No repeated reconnect matrix or long soak is
scheduled. Stop on a concrete failure and inspect that layer.

Freeze the first passing PCB firmware source, binary, hash, configuration, and
matching Pi adapter as the new functional recovery point.

### 5. Restore the existing Pi UI and camera/IMU loop

Start the existing isolated research status/UI and camera relay processes after
checking socket ownership. Run either the standalone validator or the normal
BLE agent, never both at once. Restore the private SSH browser tunnel and open
the existing page.

Use one short integrated observation, approximately 60–90 seconds: camera view
and overlay plumbing, wearable receiving state, both live IMU graphs, current
sample age, clock alignment state, and local session summary. Trigger one
bounded identify/buzzer command through the existing control path. Check the
combined workload for obvious gaps or disconnects. No UI redesign or repeated
camera benchmarks is part of this step.

### 6. Complete the physical exercise check last

Once the camera frames the full person and the PCB is mounted at the intended
lower-back orientation, use the existing countdown/person-pose test for one
short run. The previous 30-second person run received 217 frames and detected
no pose; real video alone therefore cannot satisfy this check.

Then inspect real rep boundaries, the three phase records, synchronization and
calibration eligibility. Retain the existing V5 feature/unit/pose validity
checks: current code does not yet establish live scoring eligibility. A PCB
stream pass cannot resolve training IMU provenance or pose equivalence. Report
the exact remaining blocker if a real prediction is still unavailable. The
already validated fixed-input model result is separate from live exercise
analysis and does not need another benchmark for this pin change.

## Completion and rollback

Report firmware hash/version, actual pin map, MPU identity/configuration,
measured packet count/rate/gaps/errors, owner-observed LED/buzzer results,
Pi UI/camera/graph results, and the separate status of mounted rep/model checks.
No gate is marked complete from a mock or an older-board measurement.

The retained automatic PCB actuator image can restore the proven electrical
test. The archived R9 binary expects the old sensor pins and NeoPixel and is
not a functional rollback for the assembled PCB. After step 4, the passing
PCB application becomes the functional rollback. Restore only the changed Pi
files/processes from their snapshot if necessary.

The initial planning pass used only read-only Pi/Windows inventory. Subsequent
implementation progress is recorded in the M2-07 evidence report; historical
planning observations above are not new hardware acceptance results. Changes
remain uncommitted.
