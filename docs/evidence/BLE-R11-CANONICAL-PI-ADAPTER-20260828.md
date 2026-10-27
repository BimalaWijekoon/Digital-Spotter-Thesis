# R11 canonical Pi BLE adapter evidence

**Date:** 2026-08-28

**Work package:** `PLAN.md` M2-02 / R11

**Environment:** E0 unit tests and E3 Raspberry Pi 4B + ESP32-C3 + MPU6500 bench

**Result:** PASS for the scoped R11 adapter; system-image installation and M2-04
clock mapping remain later gates

## Scope

R11 adds the canonical Pi owner for the unchanged, frozen R9 research firmware.
The ESP was not reflashed, reset, paired, bonded, or modified. The Pi candidate was
tested from `/home/pibimalawijekoon/digital-spotter-r11-candidate`; it did not
replace Wi-Fi, SSH, Tailscale, BlueZ configuration, or an installed product service.

The active adapter:

- discovers only BLE name `ESP32-C3-Test` and public address
  `50:78:7D:92:61:1A`;
- verifies the exact R9 service and four characteristic UUIDs;
- requests no pairing or bonding;
- validates exact device information, bounded status, and the 20-byte stream;
- owns one Bleak client with bounded reconnect backoff of 2, 4, 8, then 15 seconds;
- uses a 16-packet drop-oldest ingress queue and a one-value latest-sample slot;
- publishes canonical `IMUSample` events over the existing UDS framing boundary;
- reports rate, age, gaps, duplicates, invalid packets, ingress drops, I2C errors,
  connection failures, reconnects, publisher failures, and device/stream state.

R9 resets its raw u16 sequence to zero for every acknowledged `stream:start`.
R11 therefore begins a new raw-sequence epoch only after the start command is
acknowledged. ESP uptime/boot identity is not falsely reset.

## Source identity

| File | SHA-256 |
|---|---|
| `src/digital_spotter/imu/r9_protocol.py` | `4e59c2cc62289c2f062f03807a0880d2ec46a04eef75c10df4680d80822add10` |
| `src/digital_spotter/imu/r9_agent.py` | `2357d8e4543f91eded31b0b2de7ce283f50c68059588962d735e0d8adf3b22c4` |
| `src/digital_spotter/imu/r9_transport.py` | `a897ec6251ca212903dd580894b47ab388e667a70fc6df3c29f9a4db1d38b58c` |
| `src/digital_spotter/imu/r9_runtime.py` | `775c995c33bea9cd9595034cc6dcb21843b9b54eddbef1c58405ef4e4d679236` |
| `src/digital_spotter/imu/r9_bench.py` | `9e1ec7eb0bc17cfea33c5b618281fd3affca847899d298620e796c7fc0dff399` |
| `scripts/ds-imu.service` | `098a96bcb2716224e72c18043fc2c45f937f2c3bf0553d0686e8fabdf283fafc` |

These hashes were recorded before the documentation-only follow-up. Recalculate
them if any implementation file changes.

## Deterministic verification

- Focused R11 tests after the final reconnect changes: 17 passed.
- Final full repository suite: 209 passed, 7 pre-existing deprecation warnings,
  in 62.18 seconds.
- `git diff --check`: passed at handoff.
- The unchanged frozen R9 validator was rerun twice as a regression oracle: 761
  and 760 measured packets near 50 Hz, with zero gaps, I2C errors, and disconnects.

The model validator was also attempted but could not load the model because this
local `.venv` contains neither TensorFlow 2.16.2 nor `ai_edge_litert`. That is an
environment dependency blocker, not an R11 pass, and is not represented as one.

## Real-hardware results

Pi preflight reported Bluetooth powered, discovery idle, `throttled=0x0`, and no
competing BLE client.

### Focused 10-second stream

| Metric | Result |
|---|---:|
| samples | 501 |
| observed duration | 10.000466 s |
| observed rate | 50.053723 Hz |
| latest sample age | 22.206 ms |
| gaps / duplicates / invalid | 0 / 0 / 0 |
| notification drops / I2C errors | 0 / 0 |
| connection failures / reconnects | 0 / 0 |

### Controlled disconnect/reconnect

One established link was deliberately disconnected in software. The adapter
recovered without pairing, reset, global BlueZ deletion, firmware change, or owner
intervention. BlueZ required two bounded reconnect cycles before the link remained
stable. Transition loss stayed explicit: 84 queued notifications were discarded
during the intentional outage/recovery and were reported separately from the
steady-state measurement.

After stability, the 10-second measurement delivered 502 packets at 50.075473 Hz,
latest age 0.965 ms, with zero steady-state gaps, duplicates, invalid packets,
notification drops, I2C errors, or publisher failures.

### Two-minute uninterrupted stream

| Metric | Result |
|---|---:|
| samples | 6,003 |
| observed duration | 120.000838 s |
| observed rate | 50.064697 Hz |
| latest sample age | 24.236 ms |
| gaps / duplicates / invalid | 0 / 0 / 0 |
| notification drops / I2C errors | 0 / 0 |
| connection failures / reconnects | 0 / 0 |
| publisher failures | 0 |

## Failures found and corrected

1. Bleak can emit callbacks for transient internal connection attempts. Only the
   accepted client may now signal an established-link disconnect.
2. A one-entry callback queue dropped short BlueZ bursts. The ingress queue is now
   bounded at 16 while the public latest-sample slot remains one value.
3. R9 restarts sequence at zero per stream. R11 now treats acknowledged
   `stream:start` as the sequence epoch boundary and discards only pre-ack data.
4. Reconnect evidence now separates transition loss from the stable post-recovery
   measurement instead of hiding either one.

## Remaining gates

- The systemd unit is source- and contract-tested but was not installed or
  boot-tested on the Pi in this slice.
- The real bench used the counting evidence publisher; the UDS codec/publisher is
  covered by deterministic tests, while live `ds-core` consumption remains an
  integration task.
- R9 data remains uncalibrated and marked degraded/acquiring. M2-04 owns ESP-to-Pi
  clock mapping, stale policy, wrap/reset handling, and alignment evidence.
- Gym mounting/RF and final G2 soak remain M2-06; this focused R11 run is not that
  gate.
