# ESP32-C3 wearable firmware

This is the main wearable application. Version `0.9.1-pcb1` adapts the frozen
R9 Arduino BLE/50 Hz behavior to the assembled ESP32-C3/MPU6500 PCB. The frozen
R9 checkpoint remains unchanged. Temporary electrical diagnostics are separate
under `firmware/imu_pcb_bringup/`.

## Active files

| File | Purpose |
|---|---|
| `esp32_c3_research.ino` | Arduino firmware source, version `0.9.1-pcb1` |
| `board_config.h` | Assembled-PCB GPIO map |
| `pi_ble_r9_actuator_test.py` | Matching Raspberry Pi BLE/IMU/actuator validator |
| `checkpoints/r9/pass/` | Compact, hash-verified golden recovery checkpoint |

Older R0-R8 scripts, generated build directories, failed candidates, MQTT
firmware, the ESP-IDF recovery candidate, and the one-off BLE diagnostic sketch
were removed with explicit owner approval on 2026-08-28. Their useful measured
history remains in `docs/BLE_RESEARCH_BRINGUP_PLAN.md`, `docs/evidence/`, and Git
history where previously tracked.

## Hardware contract

- ESP32-C3, 4 MB flash
- MPU6500 at I2C address `0x68`, exact `WHO_AM_I=0x70`
- SDA GPIO18, SCL GPIO19; 100 kHz I2C
- external common-ground RGB: red GPIO1, green GPIO0, blue GPIO3; active HIGH
- active buzzer: GPIO10 into Q7 driver; positive J6.1, switched return J6.3
- BLE name `ESP32-C3-Test`
- public address observed on the research board `50:78:7D:92:61:1A`

The current BLE profile is deliberately open research mode: no pairing, bonding,
Wi-Fi, MQTT, provisioning, or application authentication. It exposes real sensor
data plus bounded harmless research controls. Do not describe this image as
production-secure.

## Application behavior

- exact device, status, control, and stream GATT roles from
  `docs/INTERFACES.md`;
- explicit `stream:start` and `stream:stop`;
- real, uncalibrated 20-byte MPU6500 packets at approximately 50 Hz;
- bounded reconnect/advertising recovery;
- white boot, blue advertising, green idle, cyan streaming, orange disconnect,
  and red sensor-error external RGB states, using hardware PWM;
- one non-blocking 500 ms HIGH/LOW active-buzzer test cue;
- compile-time actuator rollback through `DS_ENABLE_ACTUATOR_CUES=0`.

The IMU remains ±2 g, ±250 °/s, DLPF=3, 50 Hz. Startup verifies the written
configuration by register readback. The 20-byte raw-count packet is unchanged.
The Pi explicitly accepts `0.9.0-r9` and `0.9.1-pcb1` identities; unknown
identities remain rejected. RGB/buzzer tests run only when requested; the
automatic electrical-test loop is not included in the application.

## Build and flash

Use the frozen toolchain from the R9 manifest:

- Arduino IDE 2.3.10 or Arduino CLI 1.5.1;
- Arduino-ESP32 3.3.10;
- board/FQBN `esp32:esp32:esp32c3`.

PCB1 uses the core's PWM API and needs no external LED/sensor library. Native
USB CDC must be off because GPIO18/19 are connected to the IMU. Use the board's
USB-UART bridge. Unplug the converter before connecting ESP USB; JP1 cap stays
OFF. Remove USB before applying the documented external SYS_5V/SYS_GND supply.

Open `esp32_c3_research.ino` in Arduino IDE and flash only this sketch. Do not
erase the complete chip for an ordinary application update.

## Pi validation

Copy the matching validator to the Pi environment and run:

```bash
python pi_ble_r9_actuator_test.py --duration 30
```

The frozen real-hardware result was 1,499 packets over 30.001075 seconds at
49.964876 Hz, 14,998-24,994 microsecond sensor intervals, zero sequence gaps,
zero I2C errors, and zero unexpected disconnects. The owner physically confirmed
all LED states and the buzzer. See
`docs/evidence/BLE-R9-ACTUATOR-CUES-20260828.md`.

## PCB integration status and rollback

M2-07 is tracked in `docs/PCB_INTEGRATION_PLAN.md`. Build/upload and new-PCB
stream evidence must be reported separately from the historical R9 result above.
The archived R9 binary expects SDA5/SCL6 and a NeoPixel and is not a functional
rollback for this PCB. Retain the proven automatic PCB actuator image until a
PCB1 application checkpoint has passed.
