# BLE R4 synthetic 50 Hz evidence — 2026-08-27

## Outcome

R4 passed on the real Raspberry Pi 4B and ESP32-C3. The existing notify-only
stream carried the exact 20-byte little-endian packet at approximately 50 Hz.
The data was deliberately synthetic; the MPU6500 was not initialized.

The eight-second smoke passed with 403 packets at 50.273240 Hz. The two-minute
gate passed with:

```text
samples: 6001
average rate: 50.009585 Hz
packet length: 20 bytes for every notification
sequence gaps: 0
sensor timestamp interval: exactly 20000 us
invalid packet lengths: 0
unexpected disconnects: 0
```

All protocol versions, flags, and deterministic synthetic sensor fields matched
the independent Pi decoder. Device-info, control echo, characteristic roles,
legacy-characteristic absence, and clean disconnect also passed.

## Firmware

```text
Source SHA-256: 03bc3e6ebabbb46dd9995a845b89c355ef2bfe640310e132d818886d455e6e98
Application size: 622848 bytes
Application SHA-256: f849710760da57187d254c998aa0988b5934038de4d55e331dd5d579e8b8f48c
Framework: Arduino-ESP32 3.3.10
BLE address: 50:78:7D:92:61:1A
```

The full source/build/flash/test/rollback record is in
`firmware/esp32_c3_research/checkpoints/r4/R4_MANIFEST.md`.

## Claim boundary

R4 proves the binary BLE transport and synthetic scheduler only. It does not
prove MPU6500 detection or data, restart/reconnect reliability, buzzer behavior,
pairing, bonding, encryption, or application security.
