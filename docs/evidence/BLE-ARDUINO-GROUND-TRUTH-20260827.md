# Arduino BLE ground-truth evidence — 2026-08-27

**Environment:** E3, real Raspberry Pi 4B and real ESP32-C3
**Security mode:** plain BLE; no pairing, bonding, or application authentication
**IMU:** not initialized in this test

## Artifacts

| Artifact | SHA-256 |
|---|---|
| `firmware/esp32_c3_ble_arduino_test/esp32_c3_ble_arduino_test.ino` | `2b270349d834ff4a820ae76b6e2aa66d580aeb2ddca3004777e0eb851f65373c` |
| `firmware/esp32_c3_ble_arduino_test/pi_ble_test.py` | `3c68481a1df5e8cd105b13240d8b407c237d9af0f539a3d9682735709d95147e` |
| `firmware/esp32_c3_ble_arduino_test/README.md` | `c7def355d61e0b31f769443d3b457e88815dc02422694d385b3b8d9baec7533a` |

The exact Arduino IDE, Espressif Arduino core, Adafruit NeoPixel library, board
settings, and exported firmware binary hash were not captured in this original R0
run. They were subsequently captured by R1 in
`firmware/esp32_c3_research/checkpoints/r1/R1_MANIFEST.md` before the sketch
evolved.

## Observed Pi result

The owner ran:

```text
cd ~/ble-test
.venv/bin/python pi_ble_test.py
```

The client reported:

```text
[SCAN] Found name='ESP32-C3-Test' address=50:78:7D:92:61:1A
[BLE] Connecting without pairing or bonding...
[BLE] Connected=True
[READ] count:1
[WRITE] Hello from Raspberry Pi
[NOTIFY] handle=15 value=count:2
...
[NOTIFY] handle=15 value=count:11
[BLE] Disconnected cleanly
TEST RESULT: PASS
```

The initial read being `count:1` rather than `Hello from ESP32` is explained by
the diagnostic sketch using one characteristic for read, write, and notify: the
notification counter updates that characteristic before the read. R3 will separate
the characteristic responsibilities.

## Claims supported

- ESP32-C3 advertising and radio path work.
- Raspberry Pi Bluetooth controller, BlueZ, D-Bus, and Bleak path work.
- Plain LE connection works.
- GATT read, write with response, notifications, and clean disconnect work.
- The observed ESP address is `50:78:7D:92:61:1A`.

## Claims not supported

- MPU6500 sampling or identity.
- 20-byte binary packets or 50 Hz streaming.
- repeated reconnect or reboot recovery.
- pairing, bonding, encryption, controller identity, or application security.
- camera, fusion, inference, UI, persistence, cloud, mounting, or gym behavior.

This is the active rollback/control result for the research BLE ladder. Earlier
ESP-IDF secure-BLE results remain historical evidence for their earlier artifacts;
they do not describe the currently running Arduino test firmware.
