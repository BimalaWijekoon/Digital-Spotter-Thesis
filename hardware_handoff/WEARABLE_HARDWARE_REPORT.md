# Gym Spotter wearable hardware handoff

**Inspection date:** 2026-09-10
**Repository revision inspected:** `1896ecd187051ca48c5da0777b60c9764f8dc4c8` (`main`)
**Purpose:** extract the current firmware-to-hardware contract for a socketed carrier PCB. This is not a finished schematic.

## Evidence labels

- **CODE-CONFIRMED** — present in the active firmware or frozen build configuration.
- **LOG-OBSERVED** — present in retained real-hardware logs; not re-tested for this handoff.
- **USER-REPORTED** — supplied by the owner; the hardware was not inspected in this task.
- **DOCUMENTED** — stated in an identified manufacturer or supplier document.
- **INFERRED** — a limited engineering implication, not direct proof.
- **UNKNOWN** — required information was not established.

No firmware, configuration, CAD, hardware, or existing evidence was modified. The working tree already contained unrelated M3 vision changes; the active firmware directory itself had no reported local changes before this handoff was created.

## 1. Executive handoff

The active wearable implementation is Arduino firmware version `0.9.0-r9` in `firmware/esp32_c3_research/esp32_c3_research.ino` (**CODE-CONFIRMED**, lines 1-20 and 34-47). Its electrical GPIO contract is:

| Function | ESP32-C3 GPIO | Current behavior |
|---|---:|---|
| MPU6500 SDA | 5 | I2C, 100 kHz |
| MPU6500 SCL | 6 | I2C, 100 kHz |
| RGB indicator | 8 | one WS2812/NeoPixel data signal, GRB, 800 kHz |
| Buzzer signal | 10 | Arduino `tone()`, 2.5 kHz for 120 ms on manual test |

Source: `firmware/esp32_c3_research/esp32_c3_research.ino:52-100` and `:1191-1203`.

Three matters must be resolved before the carrier schematic/footprint is released:

1. **Controller board identity — UNKNOWN.** The generic build target proves ESP32-C3 compatibility, not whether COM0293 is physically an ESP32-C3-DevKitM-1/MINI-1 board or an ESP32-C3-DevKitC-02/WROOM-02 board. Their header pin positions differ.
2. **Purchased external RGB board conflicts with current firmware — DOCUMENTED/CODE-CONFIRMED.** The current firmware expects one addressable WS2812/NeoPixel data input on GPIO 8. The supplied Duino 5050/KY-009 description identifies separate `R`, `G`, and `B` inputs with a common cathode. Those are not interchangeable. Both candidate Espressif dev boards already document an onboard addressable RGB LED on GPIO 8, so the observed firmware cues may have used that onboard LED; this task did not physically prove it.
3. **Power and module connector details — USER-REPORTED/UNKNOWN.** The overall power chain is reported, but charger pad use, protected return, connector polarity, charge-current setting, programming-power isolation, and exact module pin order/footprints are not release-ready.

The complete signal list is in `hardware_handoff/PIN_MAP.csv`.

## 2. Active firmware and build evidence

| Item | Result | Evidence |
|---|---|---|
| Wearable entry point | `firmware/esp32_c3_research/esp32_c3_research.ino` | **CODE-CONFIRMED** — `firmware/esp32_c3_research/README.md:4-11` |
| Framework | Arduino-ESP32 BLE API and Arduino `Wire` | **CODE-CONFIRMED** — source `:22-28`; `docs/INTERFACES.md:47-56` |
| Firmware version | `0.9.0-r9` | **CODE-CONFIRMED** — source `:34-47` |
| Arduino IDE / CLI | IDE 2.3.10 or CLI 1.5.1 | **DOCUMENTED** — firmware README `:48-57`; R9 manifest `:5-11` |
| Arduino-ESP32 | 3.3.10 | **DOCUMENTED** — same sources |
| Adafruit NeoPixel | 1.15.5 | **DOCUMENTED** — same sources |
| BLE and Wire libraries | bundled with Arduino-ESP32; no separately pinned library found | **CODE-CONFIRMED** |
| Arduino FQBN | `esp32:esp32:esp32c3` | **CODE-CONFIRMED** — README `:52-55`; manifest `:7-11` |
| Underlying SDK snapshot | ESP-IDF 5.5.4, target `esp32c3`, RISC-V, Arduino variant `esp32c3` | **CODE-CONFIRMED** — `.../checkpoints/r9/pass/artifacts/sdkconfig:1-4`, `:292-300`, `:502-508` |
| Flash | 4 MB configuration | **CODE-CONFIRMED** — sdkconfig `:464-472`; **LOG-OBSERVED** — `docs/CURRENT_STATE.md:64-72` |
| PlatformIO environment | not found | **UNKNOWN/not implemented** |
| Standalone ESP-IDF project | not active; no firmware `CMakeLists.txt` target found | **UNKNOWN/not implemented** |
| Frozen source identity | active `.ino` byte-identical to R9 checkpoint; SHA-256 `5cf7f44400954611d307093503e710840576a6d5f5fff169e25f5753fae2283b` | **CODE-CONFIRMED** by file comparison |
| Frozen application binary | 666,560 bytes; SHA-256 `4432368b23dd2cf04f1fc528a1b2fadd769015ddd1834cd473f25f06f2697ea3` | **DOCUMENTED/CODE-CONFIRMED** — R9 manifest `:13-35` and retained artifact |

The build target does **not** prove the physical development-board model.

### Plausible controller boards

The [Duino COM0293 listing](https://www.duino.lk/product/esp32-c3-devkitc-02-development-board/) is internally inconsistent: it uses DevKitC-02, DevKitM-1, WROOM-02, and MINI-1 descriptions. Treat it as purchasing context, not a footprint authority.

| Candidate | Manufacturer documentation | Conditional positions for active GPIOs |
|---|---|---|
| ESP32-C3-DevKitM-1 / ESP32-C3-MINI-1 | [Espressif DevKitM-1 guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c3/esp32-c3-devkitm-1/user_guide.html) and [official dimension drawing](https://dl.espressif.com/dl/schematics/DIMENSION_ESP32-C3-DEVKITM-1_V1_20200915AA.pdf) | GPIO5 `J3-10`; GPIO6 `J3-9`; GPIO8/onboard RGB `J3-6`; GPIO10 `J1-11` |
| ESP32-C3-DevKitC-02 / ESP32-C3-WROOM-02 | [Espressif DevKitC-02 guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c3/esp32-c3-devkitc-02/user_guide.html) and [official dimension drawing](https://dl.espressif.com/dl/schematics/DXF_ESP32-C3-DevKitC-02_V1_1_20210121AA.pdf) | GPIO5 `J1-7`; GPIO6 `J1-8`; GPIO8/onboard RGB `J1-11`; GPIO10 `J3-7` |

Do not create a carrier footprint from this conditional table. First photograph/read reliable module and PCB markings, count the headers, and compare the physical board to the applicable official drawing.

## 3. Signal and connection contract

### IMU

| Signal | Contract | PCB meaning |
|---|---|---|
| SDA | GPIO5, I2C | route to the IMU module SDA pin |
| SCL | GPIO6, I2C | route to the IMU module SCL pin |
| AD0 | no GPIO/control found; firmware always addresses `0x68` | module must present address `0x68`; actual board pull state must be inspected |
| INT | not implemented | do not assign a GPIO unless firmware is intentionally changed later |
| NCS/chip select | not implemented | SPI is not used; verify the module itself holds the sensor in I2C-compatible state |
| FSYNC | not implemented | no connection required by current firmware |
| reset/sync | not implemented | no connection required by current firmware |
| SPI SCLK/MOSI/MISO/CS | no alternative SPI implementation found | do not assign convenient defaults |

GPIO5 and GPIO6 are also ESP32-C3 JTAG functions MTDI and MTCK. The carrier may use them for I2C as the firmware does, but that prevents simultaneous use of those pins for the default JTAG interface.

### Indicator

The active code constructs one `Adafruit_NeoPixel` on GPIO8 using `NEO_GRB + NEO_KHZ800`, count 1, brightness 48/255 (`esp32_c3_research.ino:52-55` and `:97-101`). Initialization clears the pixel and then shows the white boot cue (`:1090-1100`). It is an addressable 800 kHz data protocol, not three firmware PWM channels.

Current cues (`:490-517`, `:531-639`):

- white boot for 800 ms;
- blue breathing while advertising, 1.6 s cycle;
- green connected/idle;
- cyan streaming;
- orange disconnect for 500 ms;
- red sensor/error state;
- amber read for 180 ms, magenta write for 300 ms, cyan notification for 120 ms when not overridden by streaming;
- white identify for 900 ms.

The purchased [Duino 3-colour RGB SMD LED/KY-009 module](https://www.duino.lk/product/3-colour-rgb-smd-led-board-module/) is described as a 5050 common-cathode module with separate R/G/B inputs and current-limiting resistors. **No R, G, or B GPIOs exist in the active firmware.** The PCB designer needs one explicit choice:

- use only the controller's onboard GPIO8 addressable RGB;
- fit an external WS2812-compatible one-wire LED/module on the GPIO8 data contract; or
- redesign both firmware and electronics for the purchased separate-channel RGB board.

That choice was not made in this handoff.

GPIO8 is also an ESP32-C3 strapping pin. The official development boards already account for their onboard RGB circuit, but a carrier must not add a pull/load that forces the boot strap. See the [ESP32-C3 datasheet](https://documentation.espressif.com/ESP32-C3_Datasheet_en.pdf).

### Buzzer

GPIO10 is configured as an output and initialized LOW (`esp32_c3_research.ino:1094-1101`). The only implemented sound uses Arduino `tone(GPIO10, 2500, 120)` (`:1191-1203`). Thus:

- control method: 2.5 kHz square-wave/tone, 120 ms;
- quiet initialization level: LOW;
- exact KY-012 input polarity, supply voltage, input current, and onboard transistor/driver: **UNKNOWN**;
- an external transistor/driver is not documented in the repository;
- code cannot prove that GPIO10 can safely drive the purchased module directly.

Retained owner observation confirms the cue was heard, but not the module's electrical construction (`firmware/esp32_c3_research/checkpoints/r9/pass/owner-cue-observation.txt:1-17`).

### Battery, charger, buttons, and power control

The firmware contains no implemented battery ADC, voltage divider, charger-status input, physical button, rocker-switch input, power-enable output, or low-battery behavior. These must not be assigned arbitrary GPIOs.

The KCD11 is **USER-REPORTED** as a two-pin SPST supply switch. It is not a firmware button.

Potentially header-exposed GPIO0-4, 7, 9, and 18-21 are unused by the application, but are not automatically free:

- GPIO2, GPIO8, and GPIO9 are boot strapping pins;
- GPIO18/19 are USB D-/D+;
- GPIO20/21 are UART0 RX/TX;
- GPIO4-7 are default JTAG signals, including current I2C GPIO5/6;
- physical availability/position depends on the controller variant.

### USB, UART, and debug

The application does not explicitly reassign USB or UART pins. `Serial.begin(115200)` is used (`esp32_c3_research.ino:1090-1092`). The frozen SDK configuration records UART0 as the default console and USB Serial/JTAG as a secondary console (`.../artifacts/sdkconfig:1735-1745`). For both controller candidates, Espressif documents:

- GPIO18 = USB D-;
- GPIO19 = USB D+;
- GPIO20 = UART0 RX;
- GPIO21 = UART0 TX;
- GPIO9 participates in boot/download selection.

Do not load or repurpose these nets on the carrier without preserving programming and recovery access.

## 4. IMU identity and settings

The firmware does not instantiate an MPU9250/MPU6500 driver library. It performs direct register I/O through Arduino `Wire` (`esp32_c3_research.ino:195-245`).

| Item | Extracted result | Evidence |
|---|---|---|
| Bus/address | I2C, GPIO5/GPIO6, 100 kHz, address `0x68` | **CODE-CONFIRMED** — source `:65-82`, `:265-275` |
| Identity check | register `0x75` must equal `0x70`; every other value is rejected | **CODE-CONFIRMED** — source `:69-71`, `:281-305` |
| Observed identity | `WHO_AM_I=0x70` at `0x68` | **LOG-OBSERVED** — `.../esp-serial-extract.log:1-12`; `docs/CURRENT_STATE.md:64-72` |
| Power/clock | write `PWR_MGMT_1 (0x6B)=0x01` | **CODE-CONFIRMED** — source `:307-329` |
| Gyro filter config | write `CONFIG (0x1A)=0x03` | **CODE-CONFIRMED** |
| Sample divider | write `SMPLRT_DIV (0x19)=19`; firmware reads every 20 ms | **CODE-CONFIRMED** — source `:307-329`, `:414-441` |
| Gyro range | `GYRO_CONFIG (0x1B)=0x00`, ±250 dps | **CODE-CONFIRMED** |
| Accelerometer range | `ACCEL_CONFIG (0x1C)=0x00`, ±2 g | **CODE-CONFIRMED** |
| Accelerometer DLPF | `ACCEL_CONFIG2` is not written | **UNKNOWN/default state not verified** |
| Data read | 14 bytes from `0x3B`; raw accel XYZ and gyro XYZ; temperature bytes skipped | **CODE-CONFIRMED** — source `:338-353` |
| FIFO/interrupt | not used | **CODE-CONFIRMED/not implemented** |
| Calibration | none; raw counts | **CODE-CONFIRMED** — source `:8-12`; `docs/INTERFACES.md:94-98` |
| Magnetometer | not initialized or read; no access to AK8963/auxiliary I2C found | **CODE-CONFIRMED/not implemented** |

The retained log proves that the unit used in the earlier bench run answered as an MPU6500 (`0x70`). It does not prove that every purchased ML2080 module contains the same silicon. The [Duino ML2080 listing](https://www.duino.lk/product/mpu-9250-9-axis-attitude-gyro-accelerator/) calls the module MPU9250/GY-9250, while active firmware deliberately rejects MPU9250 identity `0x71` (`docs/DECISIONS.md:141-164`; `docs/INTERFACES.md:169-175`).

The current code copies sensor X/Y/Z directly into the BLE packet with no axis swap or sign inversion (`esp32_c3_research.ino:338-353`, `:684-700`). Therefore the PCB/enclosure must establish and document:

- which module edge points up/down, left/right, and forward/back when worn;
- the module PCB orientation relative to the enclosure;
- the enclosure orientation at the lower back;
- connector/keying that prevents reversed installation.

No photograph, drawing, or enclosure datum in the repository proves this physical orientation. It is **UNKNOWN** and should be silk-screened once selected.

## 5. Operating behavior relevant to electronics

| Behavior | Current implementation |
|---|---|
| Radio | local BLE peripheral/GATT server only; Wi-Fi and MQTT are intentionally not initialized (**CODE-CONFIRMED**, source `:1102-1119`; `docs/CURRENT_STATE.md:120-129`) |
| BLE security | open research BLE; no pairing, bonding, or encrypted permissions (**CODE-CONFIRMED**, source `:1018-1022`) |
| Sensor acquisition | scheduled every 20,000 µs (50 Hz configured) |
| Transmission | 20-byte BLE notification at the 20 ms schedule only while connected and `stream:start` is active (`:703-765`, `:1235-1279`) |
| Measured retained run | 1,499 packets / 30.001075 s = 49.964876 Hz; zero sequence gaps, I2C errors, or unexpected disconnects (**LOG-OBSERVED**, `.../pi-validation.log:18-41`) |
| Advertising recovery | after disconnect, 100 ms delay; maximum three attempts, 500 ms retry interval (`:90-95`, `:1026-1038`) |
| Sleep/wake | no sleep mode or wake source found |
| Battery low | no sensing or behavior implemented |
| Current/runtime | not measured or derivable from the firmware |

The code contains a stale message saying the BLE stream remains synthetic at `esp32_c3_research.ino:331-335`. Later code and retained R9 logs show the notification payload is real raw MPU6500 data (`:703-765`; `.../esp-serial-extract.log:6-12`). Treat the message as a source-text contradiction, not the active data path.

## 6. Power path: reported versus unresolved

### Reported present circuit — USER-REPORTED, not an inspected netlist

`LiPo -> TP4056 battery connection -> TP4056 output -> MT3608 input -> adjusted 5 V output -> KCD11 in positive lead -> controller supply`, with a negative connection to the controller.

The words “battery connection,” “input,” “output,” and “negative” are insufficient for PCB release. The designer must distinguish:

- TP4056 USB/input pads from cell `B+`/`B-` pads;
- protected load `OUT+`/`OUT-` from raw battery pads;
- MT3608 `VIN-`/`VOUT-` return path;
- controller 5 V and GND header pins for the confirmed board variant.

With the switch after the boost converter, the boost remains connected to the battery while the wearable is switched off.

### Proposed future change — proposal only

Switch protected charger `OUT+` before MT3608 `VIN+`, while retaining protected `OUT-` as the return. The existing hardware has not been claimed to contain this change.

### Electrical checks still required

- **Battery:** BAT0466 is **USER-REPORTED/DOCUMENTED by supplier** as 3.7 V, 1000 mAh, 30C, code 802535. Maximum allowed charge current, protection PCB, connector type/polarity, and reliable mechanical drawing are **UNKNOWN**. Do not derive a charge current solely from capacity or the model code.
- **Charger:** ML2051-5 is **USER-REPORTED/DOCUMENTED by supplier** as a TP4056 USB-C module with protection. Identify the actual `IN`, `B`, and protected `OUT` pads, fitted programming resistor/charge current, protection ICs, indicator pins, connector orientation, and board outline from the physical module.
- **Boost:** ML2060 is **USER-REPORTED** as an MT3608 adjusted to 5 V. Measure output before connecting the controller and validate current capacity, ripple, startup overshoot, and BLE/buzzer load transients. Supplier maximum ratings are not a measured node capability.
- **Programming power:** the official Espressif development-board guides state that USB, 5 V/GND, and 3V3/GND power methods are mutually exclusive. The PCB needs isolation or an explicit procedure that prevents the boost 5 V rail and USB programming supply from backfeeding each other.
- **Charging while operating:** load sharing/power-path behavior, charge termination with the load active, heat, and USB/external-supply interaction are **UNKNOWN**.
- **Logic voltage:** ESP32-C3 GPIO is 3.3 V-domain logic. A controller 5 V supply input does not make GPIO 5 V tolerant. I2C pull-ups must not expose the GPIOs to 5 V; inspect the IMU module regulator, pull-ups, and any level shifting.
- **Common ground:** IMU, indicator, buzzer, controller, boost, and protected charger return must use the deliberately selected return net. “Negative” is not a sufficient net name.

No active repository schematic, BOM, carrier CAD, documented voltage divider, RGB resistor values, buzzer driver, decoupling plan, or module connector pin-order drawing was found. Supplier descriptions are not substitutes for inspecting the purchased modules.

## 7. Minimal remaining inputs for the PCB designer

Only these unresolved items materially block a correct schematic or footprint:

1. Clear top/bottom photographs and reliable markings of COM0293; confirm DevKitM-1/MINI-1 versus DevKitC-02/WROOM-02, header count, 2.54 mm pitch, row spacing, and orientation. Then use the matching official Espressif dimension drawing.
2. Exact socket/header gender, pin count, row spacing, insertion direction, keep-outs, and pin-1 keying for every module.
3. Photograph/continuity-check the ML2080 pin labels and order; re-read `WHO_AM_I` for the exact production module if it may differ from the earlier logged unit.
4. Decide indicator hardware: onboard GPIO8 WS2812, an external one-wire WS2812, or the purchased separate R/G/B KY-009 plus a firmware/electrical redesign.
5. Identify the exact KY-012 module pin order, operating voltage, active behavior, input current, and onboard driver; select a transistor/driver if required.
6. Confirm battery connector/polarity, protected/unprotected status, maximum charge current, and actual measured dimensions.
7. Identify TP4056 `IN+/IN-`, `B+/B-`, `OUT+/OUT-`, fitted charge resistor/current, and protected return; decide whether operation while charging is allowed.
8. Decide and document power switching and USB/boost isolation, including the reported present circuit versus the proposed pre-boost switch placement.
9. Measure exact outlines, component heights, connector overhangs, mounting holes, and cable bend/strain-relief space for controller, IMU, charger, boost, battery, buzzer, RGB choice, and switch. Perspective product images are not footprint drawings.
10. Freeze the sensor-to-enclosure axis orientation and add orientation/pin-1 marks to silkscreen and assembly documentation.

Earlier project comments mentioning ESP32-S3 are stale prototype text (`inference/feature_engineer.py:27-39` and `:167-189`). The earlier MPU6050 decision is explicitly superseded by the accepted MPU6500 decision (`docs/DECISIONS.md:129-164`). Neither should be used for this carrier PCB.

## 8. Handoff boundary

This report supports schematic capture after the ten checks above. It does not certify module current limits, LiPo safety, charging behavior, RF/antenna clearance, connector reliability, enclosure fit, body-axis orientation, or regulatory compliance. Those require physical identification and electrical/mechanical validation of the purchased parts.
