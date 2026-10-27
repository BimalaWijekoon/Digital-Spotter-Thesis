# R9 PASS manifest

Date: 2026-08-28

## Toolchain

- Arduino IDE: 2.3.10
- Arduino CLI: 1.5.1, commit `01f3d4f2b`
- Arduino-ESP32: 3.3.10
- Adafruit NeoPixel: 1.15.5
- FQBN: `esp32:esp32:esp32c3`
- Target: ESP32-C3 revision v0.4, 4 MB embedded flash
- Application offset: `0x10000`

## Build

- Program report: 666403 / 1310720 bytes (50%)
- Global RAM report: 19628 / 327680 bytes (5%)
- Application binary: 666560 bytes
- Compile result: PASS, no unexpected warning output
- Flash result: PASS, written data hash verified

## SHA256

```text
5cf7f44400954611d307093503e710840576a6d5f5fff169e25f5753fae2283b  source/esp32_c3_research.ino
6acdac61ae9e2779b691cdad7cb14916f4d19b9e03936ad66600f783ea1c1f7f  source/pi_ble_r9_actuator_test.py
4432368b23dd2cf04f1fc528a1b2fadd769015ddd1834cd473f25f06f2697ea3  artifacts/esp32_c3_research.ino.bin
2683fd26b661bc909dcb8a9f05723d36c4000f9396995941a278fda409b753f7  artifacts/partitions.csv
f03d3e901e2e103a8bccd4071f59bbac02bad824b9014005ed8d17559f990f77  artifacts/sdkconfig
61c7cbea2eac28e5cbb8275e34ee748136cf1081d3e801beb35b82a6f8f1a351  pi-validation.log
bf7ab8431ac12c6c38da1b2ec660f9852f6d8fb45f8da9ee1bd8e2243979ca3c  esp-serial-extract.log
ad04c9d21003d64874ffbd1d50c93a641eafb755d81353f50d82322419004861  cue-demo.log
78f692818cf156fac822917e1f43718030ca3fc8e788c8c51b99c1e53098d815  owner-cue-observation.txt
085eff5a7621f26dfbfb2e7cfe7311ad3e71670702d9b54a9da03fd981aa5bf2  pi-final-state.txt
```

## Real-hardware result

- Device info: exact `protocol=1;firmware=0.9.0-r9;hardware=esp32-c3;imu=mpu6500;rate_hz=50`
- Measured duration: 30.001075 seconds
- Packets: 1499
- Rate: 49.964876 Hz
- Sensor interval: 14998-24994 us
- Sequence gaps: 0
- I2C errors: 0
- Unexpected disconnects: 0
- Physical cues: owner confirmed complete LED mapping and short beep
- Pi final: Bluetooth active/powered, discovery off, no connected/paired/bonded device
- Pi power: `throttled=0x0`, 53.5 C

Security remains the explicit ADR-019 open research mode. R10 was not started.

The checkpoint was compacted during the owner-approved 2026-08-28 cleanup. It
retains the directly flashable application binary, source, validator, exact
configuration, partition description, and acceptance logs. Reproducible Arduino
object files, ELF/map output, merged image, bootloader copy, and partition binary
were intentionally removed and are ignored by Git.
