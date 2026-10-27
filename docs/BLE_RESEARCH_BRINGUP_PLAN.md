# BLE research bring-up plan

**Status:** R9 frozen; R11 passed on real hardware
**Hardware:** Raspberry Pi 4B + ESP32-C3 + MPU6500
**Profile:** Reliability-first local BLE research system
**Last reviewed:** 2026-08-28

## 1. Current ground truth

Do not restart from an old firmware generation. The retained ground truth is:

| Item | Frozen value |
|---|---|
| ESP source | `firmware/esp32_c3_research/esp32_c3_research.ino` |
| Source SHA-256 | `5cf7f44400954611d307093503e710840576a6d5f5fff169e25f5753fae2283b` |
| Pi validator | `firmware/esp32_c3_research/pi_ble_r9_actuator_test.py` |
| Validator SHA-256 | `6acdac61ae9e2779b691cdad7cb14916f4d19b9e03936ad66600f783ea1c1f7f` |
| Application binary | `firmware/esp32_c3_research/checkpoints/r9/pass/artifacts/esp32_c3_research.ino.bin` |
| Binary SHA-256 | `4432368b23dd2cf04f1fc528a1b2fadd769015ddd1834cd473f25f06f2697ea3` |
| Firmware version | `0.9.0-r9` |
| BLE name | `ESP32-C3-Test` |
| Observed address | `50:78:7D:92:61:1A` |
| Sensor | MPU6500 at `0x68`, exact `WHO_AM_I=0x70` |
| Stream | real raw 20-byte packets, approximately 50 Hz |

The corrected real-hardware R9 gate received 1,499 packets over 30.001075 seconds
at 49.964876 Hz, with 14,998-24,994 microsecond sensor intervals, zero sequence
gaps, zero I2C errors, and zero unexpected disconnects. The owner confirmed every
NeoPixel cue and the short buzzer. See
`docs/evidence/BLE-R9-ACTUATOR-CUES-20260828.md`.

R0-R8 stage scripts/checkpoints and abandoned firmware implementations were
removed with explicit owner approval after R9 was frozen. Their useful validation
history remains under `docs/evidence/`.

## 2. Frozen R9 contract

R9 provides:

- one Arduino-ESP32 GATT server;
- read-only device information;
- read-only bounded status;
- bounded read/write controls;
- notify-only real MPU6500 stream;
- explicit start/stop;
- sequence and sensor-capture timestamp fields;
- bounded advertising recovery;
- non-blocking GPIO 8 NeoPixel states;
- manual/test-only GPIO 10 buzzer.

R9 deliberately does not provide:

- pairing or bonding;
- Wi-Fi or MQTT;
- provisioning or controller binding;
- HMAC/HKDF application authentication;
- calibrated units or body-frame orientation;
- model-derived feedback.

Do not change R9 while implementing its Pi adapter. The compile-time
`DS_ENABLE_ACTUATOR_CUES=0` switch remains the actuator rollback.

## 3. Engineering method

For each next slice:

1. Start from the R9 source and contract.
2. Change one capability.
3. Run deterministic tests.
4. Run the smallest real-hardware test that proves that capability.
5. Record exact source/binary hashes and results.
6. Commit/tag the passing slice before adding another capability.

On failure, preserve the relevant ESP serial, Pi output, BlueZ/kernel diagnostics,
and exact source SHA. Change one variable. Do not respond by repeatedly pairing,
erasing flash/NVS, changing frameworks, or deleting global BlueZ state.

## 4. R10 — optional standard bonding decision

R10 is not required for the current controlled bench. Choose only one profile:

- **Open research mode:** retain R9, validate expected name/address/UUIDs, and
  document that a nearby device could connect.
- **Bonded research mode:** add standard BLE Secure Connections/Just Works with one
  Pi. Do not add custom HMAC/HKDF or controller provisioning in the same slice.

If bonded mode is chosen, pass one fresh pair, reconnect without re-pairing, ESP
reboot/reconnect, Bluetooth-service restart/reconnect, and Pi reboot/reconnect.
Normal boot must never clear a bond because an application state is missing.

Until the owner explicitly selects bonded mode, R10 remains skipped and R9 stays
the active firmware.

## 5. R11 — canonical Pi BLE adapter

R11 is the required next slice and should primarily change Pi code.

### Responsibilities

- one process owns BlueZ/Bleak state;
- discover only the expected R9 name/address and verify the service/UUID contract;
- connect without pairing under the current profile;
- strictly parse the exact 20-byte packet;
- expose bounded latest-sample delivery rather than an unbounded queue;
- use Pi monotonic receipt time and preserve ESP sensor time separately;
- report sample age, rate, sequence gaps, invalid packets, I2C flags, reconnects,
  and degraded/disconnected states;
- implement graceful start/stop and bounded reconnect backoff;
- never replace missing sensor data with zeros;
- never make network/cloud availability part of the live sensor path.

### Tests

1. Unit-test valid, malformed, stale, duplicate, wrapped, and sequence-gap packets.
2. Test queue bounds and latest-sample behavior with a deterministic fake
   transport.
3. Test start, stop, cancellation, reconnect backoff, and health transitions.
4. Run the standalone R9 validator unchanged as a regression oracle.
5. Run the canonical adapter against the real ESP for 2-5 minutes.

### Pass criteria

- exact identity/UUID checks pass;
- all accepted packets are exactly 20 bytes;
- approximately 50 Hz with explicit measured rate;
- zero unexplained gaps, invalid packets, or disconnects in the focused run;
- queues remain bounded;
- disconnect/reconnect returns to ready without pairing or manual BlueZ cleanup;
- no mock result is represented as real hardware.

### R11 result — 2026-08-28

PASS. The active implementation is under `src/digital_spotter/imu/r9_*.py`, and
`ds-imu-agent` selects it. Deterministic tests cover strict parsing, exact
identity/GATT validation, bounded queue/latest-sample behavior, transient Bleak
callbacks, initial connection failure, and established-link reconnect.

The final uninterrupted E3 run delivered 6,003 packets over 120.000838 seconds at
50.064697 Hz with zero gaps, duplicates, invalid packets, notification drops,
connection failures, reconnects, publisher failures, or I2C errors. A controlled
disconnect required two bounded reconnect cycles, then delivered a stable 502
packets over 10.000465 seconds at 50.075473 Hz with zero steady-state errors.
Recovery-transition drops remain explicitly counted. Full evidence is in
`docs/evidence/BLE-R11-CANONICAL-PI-ADAPTER-20260828.md`.

The R9 raw sequence restarts at zero for each `stream:start`; R11 treats the
acknowledged start response as a new raw-sequence epoch without inventing an ESP
reboot. Ingress is bounded at 16 packets with drop-oldest semantics, while the
consumer-facing latest slot holds one sample. Reconnect backoff is capped at 2, 4,
8, then 15 seconds.

### Rollback

Disable the canonical adapter and run the retained standalone R9 validator. Do not
modify or erase the ESP.

## 6. M2 hardware exit

For the research project, M2 exits after R9 and R11 pass together:

```text
ESP32-C3/MPU6500 R9
    -> local BLE
    -> one canonical Pi adapter
    -> bounded real samples and explicit health
```

Required evidence:

- exact MPU6500 identity and wiring;
- real 20-byte notifications near 50 Hz;
- sequence/timestamp continuity;
- bounded reconnect behavior;
- visible/audible actuator cues;
- Pi adapter queue/health tests;
- one short integrated hardware run;
- no MQTT or internet dependency;
- no pairing/bonding claim unless R10 is intentionally selected and passed.

Mounting calibration, body-frame transformation, fusion/model semantics, and gym
RF/thermal testing are later gates. Lower-back IMU motion is not direct barbell
velocity or power.

## 7. Golden checkpoint rule

Each future passing stage may retain one compact checkpoint containing:

- source and matching validator;
- directly flashable application binary when hardware changed;
- exact configuration/partition description;
- concise test logs and manifest hashes.

Do not commit Arduino build directories, object archives, ELF/map output, merged
images, duplicate bootloaders, or failed-candidate binaries. Those are reproducible
and are ignored by Git.
