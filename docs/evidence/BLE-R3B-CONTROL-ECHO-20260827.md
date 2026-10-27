# BLE R3B control-echo evidence — 2026-08-27

## Outcome

R3B passed on the real Raspberry Pi 4B and ESP32-C3. It added one bounded,
read/write-with-response control characteristic while preserving R3A device info
and the existing notification path.

```text
Control UUID: 7f725422-d560-4852-96d8-3407f417b1d8
Initial read: ready
Request: hello-r3b
Readback: echo:hello-r3b
Result: PASS
```

The Pi also verified that the control characteristic does not expose
write-without-response, notify, or indicate. The R3A device-info characteristic
remained read-only and returned `protocol=1;firmware=0.3.1-r3b`.

## Firmware

```text
Source SHA-256: 451fa7e2bc59aa6475a4887024293115f96972f449cd9fcd111243464deb0ea2
Application size: 623296 bytes
Application SHA-256: 2a936e285a17338a823b941c96d907e62a9580ef10ea9b751f7840d9678ac81e
Framework: Arduino-ESP32 3.3.10
BLE address: 50:78:7D:92:61:1A
```

The full source/build/flash/test/rollback record is in
`firmware/esp32_c3_research/checkpoints/r3b/R3B_MANIFEST.md`.

## Claim boundary

The valid echo path was tested on hardware. The error responses for invalid or
oversized input were not hardware-tested. R3B does not yet prove a dedicated
stream characteristic, binary/50 Hz data, MPU6500 operation, restart reliability,
buzzer behavior, or BLE security.
