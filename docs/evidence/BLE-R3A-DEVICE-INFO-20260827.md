# BLE R3A device-information evidence — 2026-08-27

## Outcome

R3A passed on the real Raspberry Pi 4B and ESP32-C3. It added exactly one
read-only GATT characteristic while preserving the passing R1/R2 characteristic.

```text
Device info UUID: e193acb8-25ef-422c-b3e5-972eae75b8ea
Properties: read only
Value: protocol=1;firmware=0.3.0-r3a
```

The Pi confirmed the exact value and characteristic properties, then successfully
read, wrote, received a notification from, and cleanly disconnected from the
unchanged R1/R2 characteristic. The final result was `TEST RESULT: PASS`.

## Firmware

```text
Source SHA-256: eb986b3775af6f227c13df9bae2e2bf2eb4995d6d75a74d0776b8be67bd9c14e
Application size: 621376 bytes
Application SHA-256: 3ab03492d5cca16ab83ea0eed6824508e80566669e8566777d9bfb37fc1aed63
Framework: Arduino-ESP32 3.3.10
ESP: ESP32-C3 revision v0.4, 4 MB flash
BLE address: 50:78:7D:92:61:1A
```

The complete build, flash, serial, test, hashes, rollback, and serial-monitor
control-line finding are recorded in
`firmware/esp32_c3_research/checkpoints/r3a/R3A_MANIFEST.md`.

## Claim boundary

This does not yet prove separate control/stream characteristics, binary or 50 Hz
notifications, MPU6500 operation, restart reliability, buzzer behavior, or BLE
security.
