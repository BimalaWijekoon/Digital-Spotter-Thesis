# PCB1 short-stream checkpoint

Date: 2026-10-19. Firmware: `0.9.1-pcb1`, protocol 1.
Scope: uploaded application, MPU6500 startup and short real BLE stream **PASS**.
Physical colour/sound replay, mounted motion/pose/rep and live model acceptance
are **not** included in this pass.

## Toolchain and wiring

- Arduino CLI 1.5.1 (`01f3d4f2b`); Arduino-ESP32 3.3.10.
- FQBN `esp32:esp32:esp32c3`; native USB CDC disabled; CP210x USB-UART.
- ESP32-C3 rev 0.4, 4 MB flash; app0 `0x10000`, size `0x140000`.
- SDA18/SCL19; MPU6500 0x68, WHO_AM_I 0x70, 100 kHz I2C.
- 50 Hz, ±2 g, ±250 °/s, DLPF 3; all profile registers read back.
- External active-HIGH RGB: R1/G0/B3, LEDC 5 kHz/8 bit, brightness 96/255.
- Active buzzer GPIO10 through existing PCB driver, bounded 500 ms HIGH pulse.
- BLE research profile remains open: no pairing/bonding/provisioning introduced.

## Build and real result

Application: 664,224 bytes; program usage 664,069/1,310,720 bytes,
global RAM 19,596/327,680 bytes. App-only flash hash verified; no NVS,
bootloader or partition-table erase. Compile reported no firmware warnings.

One externally powered 30.000815 s Pi stream delivered 1,499 samples at
49.965309 Hz, zero sequence gaps, invalid packets, I2C errors or unexpected
disconnects. Sample intervals were 15,011–24,988 us. The timed buzzer request
and deferred identify did not interrupt sampling. The owner missed the physical
cue observation and requested replay later. One clean disconnect followed by
connection from the normal Pi receiver succeeded.

## Exact retained files

```text
721251dd3de0a4ddddc8e1b9262be22ef66f873372ed641a961d4b25810dd8c4  source/board_config.h
0f51c15f68e4b14be3dd1dedb9fd654b3fb61bd37559846b2a708565186873f9  source/esp32_c3_research.ino
12171718f25478d28c4d9b255faef4bc1dbfcd5b88efe195cf2cdd717676b6ab  source/pi_ble_r9_actuator_test.py
a40dee6dddc4092e34d5dfe2afa0f29038c5206ac99cadeb7300d32a028f8ee5  source/r9_protocol.py
e6d1842ab5cb97612d8c2a3fcf16d37f292d1b5b3c1de594657173646d4011b7  artifacts/esp32_c3_research.pcb1.bin
2683fd26b661bc909dcb8a9f05723d36c4000f9396995941a278fda409b753f7  artifacts/partitions.csv
f03d3e901e2e103a8bccd4071f59bbac02bad824b9014005ed8d17559f990f77  artifacts/sdkconfig
```

Evidence: [M2-07 report](../../../../../docs/evidence/M2-07-PCB-INTEGRATION-20261019.md),
including the serial boot and portable Pi validator logs. These remain in the
evidence directory rather than duplicated here. ELF/map/intermediate build files
are generated and not part of this compact checkpoint.

## Rollback

Restore this source together with `board_config.h` and the matched Pi parser.
With current USB-only power/wiring confirmation, the retained application can
be written to the verified app0 offset without erasing NVS. Never energize ESP
USB and the converter simultaneously. The older R9 image uses incompatible
pins/NeoPixel and is not a functional rollback for this PCB.

This checkpoint and related workspace changes are uncommitted; no Git tag or
push was performed. No live-scoring readiness is implied.
