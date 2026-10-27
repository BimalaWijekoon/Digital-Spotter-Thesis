# BLE R1/R2 plain-link evidence — 2026-08-27

## Outcome

The minimal Arduino BLE baseline is now reproducible and passed the first bounded
reliability gate on the real Raspberry Pi 4B and ESP32-C3.

| Gate | Result |
|---|---|
| R1 stronger end-to-end assertion run | PASS |
| R2 scan/connect/read/write/notify/disconnect | PASS, 10/10 |
| Pi Bluetooth service after R2 | active |
| Pi discovery after R2 | off |
| Pairing/bonding/security | not used |
| MPU6500/50 Hz data | not tested |

## Reproducible firmware

- Source: `firmware/esp32_c3_research/esp32_c3_research.ino`
- Source SHA-256: `2b270349d834ff4a820ae76b6e2aa66d580aeb2ddca3004777e0eb851f65373c`
- Arduino IDE: 2.3.10
- Arduino CLI: 1.5.1, commit `01f3d4f2b`
- Arduino-ESP32 core: 3.3.10
- Compiler: `riscv32-esp-elf-g++ 14.2.0`, Espressif crosstool-NG build
  `esp-14.2.0_20260121`
- FQBN: `esp32:esp32:esp32c3`
- Application binary: 620544 bytes
- Application SHA-256:
  `505beebdfc4f39eaa2981b7c7a7b8acf217bce55ffe6104e325418d534c9b86b`

The complete binary, ELF, map, partition, tool, and board-option record is in
`firmware/esp32_c3_research/checkpoints/r1/R1_MANIFEST.md`.

## Real test environment

```text
Pi hostname: pidigitalspotter
Pi Tailscale IP: 100.104.28.69
Bluetooth service: active
Controller: powered
Discovery before and after tests: off
Bleak: 3.0.2
ESP BLE name: ESP32-C3-Test
ESP BLE address: 50:78:7D:92:61:1A
```

No second `bluetoothctl`, Bleak, or Python BLE client was running during either
test.

## R1 result

The strengthened client verified the exact name/address, connection, non-empty
read, write with response, three valid monotonically increasing counter
notifications, and clean disconnect. It ended with `TEST RESULT: PASS`.

## R2 result

`pi_ble_r2_cycle_test.py` ran ten complete bounded cycles. Every cycle performed a
fresh scan, exact-address check, connection, read, acknowledged write, valid
notification, and clean disconnect. It ended with:

```text
TEST RESULT: PASS — 10/10 cycles
```

Immediately afterward Bluetooth remained active/powered, discovery was off, no
BLE client was left running, and the bounded journal/kernel error search was
empty. The ESP counter increased across all cycles, so no reboot was observable
from the client. Serial reset-cause logging was not captured in this run.

## Claim boundary

This evidence proves only the plain BLE and basic GATT transport used by R1/R2. It
does not prove split GATT roles, binary/50 Hz data, MPU6500 operation, reconnect
after an ESP/Pi service restart, LED/buzzer concurrency, or any security feature.
