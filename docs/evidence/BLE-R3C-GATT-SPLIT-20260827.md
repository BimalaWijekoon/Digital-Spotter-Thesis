# BLE R3C GATT role-split evidence — 2026-08-27

## Outcome

R3C passed on the real Raspberry Pi 4B and ESP32-C3. The Pi verified three
non-overlapping characteristic roles under the existing service:

```text
device info: read-only
control: read + write-with-response
stream: notification-only
legacy all-in-one characteristic: absent
```

The control request `hello-r3c` returned the exact response
`echo:hello-r3c`. The stream delivered `count:2`, `count:3`, and `count:4` in
monotonic order before a clean disconnect. The device-info value was
`protocol=1;firmware=0.3.2-r3c`.

## Firmware

```text
Source SHA-256: 370d18ea73bacb7b8bd156502056affb3e7506092584432c27a428b62c92bf91
Application size: 622400 bytes
Application SHA-256: 3d3bf0deabd1bcd03fb9c30327e7fe0e117f861bd8f050c11718d1e0cd2f5739
Framework: Arduino-ESP32 3.3.10
BLE address: 50:78:7D:92:61:1A
```

COM7 upload and flash verification passed. No whole-chip or NVS erase was
performed. The full source/build/flash/test/rollback record is in
`firmware/esp32_c3_research/checkpoints/r3c/R3C_MANIFEST.md`.

## Claim boundary

R3C proves the GATT role split and the temporary two-second text-notification
path. It does not prove the R4 20-byte/50 Hz stream, MPU6500 operation,
reconnect/restart reliability, buzzer behavior, pairing, bonding, encryption,
or application security.
