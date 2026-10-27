# Assembled-PCB IMU bring-up

This is a temporary diagnostic based on the owner's
`Gym_Spotter_Updated_Pin_Config_and_IMU_Test.zip` handoff. The original identity
scan was extended to print real motion data over USB serial. It does not replace
the frozen R9 source or prove the full BLE/50 Hz motion path.

Open `IMU_Bringup/IMU_Bringup.ino` in Arduino IDE with its adjacent
`pin_config.h`. Use an ESP32-C3 target, the USB-UART bridge, native USB CDC off,
and 115200 baud. The new PCB uses SDA GPIO18 and SCL GPIO19 at 100 kHz; the
earlier R9 GPIO5/GPIO6 wiring is not valid for this board.

Before USB programming, physically unplug the converter-to-PCB connector. Keep
JP1 cap off. Fit only the ESP and correctly oriented IMU; leave external RGB and
buzzer unplugged. GPIO18/19 are also native USB data pins, so use the separate
USB-UART bridge. Never apply 5 V to the IMU VCC or ESP GPIO.

At boot, the sketch requires `WHO_AM_I=0x70` at address `0x68`, wakes all axes,
sets the accelerometer to +/-2 g and gyroscope to +/-250 degrees/s, and verifies
each configuration register by readback. It sets a 20 Hz sensor output rate and
prints AX/AY/AZ in g, GX/GY/GZ in degrees/s, and acceleration magnitude in g at
roughly 20 lines/s. It does not calibrate sensor bias or body orientation.

These register meanings and scale factors follow the
[MPU-6500 register map](https://invensense.tdk.com/wp-content/uploads/2015/02/MPU-6500-Register-Map2.pdf)
and [product specification](https://invensense.tdk.com/wp-content/uploads/2020/06/PS-MPU-6500A-01-v1.3.pdf).

The handoff ZIP's README is authoritative for the full socket, supply, and
assembly map. The mounted PCB and power isolation still require physical checks.

## Observed on the connected board (2026-10-17)

Built with Arduino-ESP32 3.3.10 for `esp32:esp32:esp32c3`; flashed only the
application at `0x10000` through CP210x COM7. The 325,440-byte binary had SHA256
`2f87c6fe7de48a27a87ebfc5ed0ebbf46a8ba44b6a4cf898a307e8b43b983f76`.
esptool verified the written image. Two serial scans reported idle SDA/SCL high,
exactly one I2C device at `0x68`, and `WHO_AM_I=0x70` (MPU6500 identity). This
proves the digital bus and identity only; motion, external RGB, buzzer, and the
converter/battery supply remain untested.

A pre-flash 4 MB image is retained locally at
`local_backups/before_imu_pcb_diagnostic_20261017.bin` (ignored by Git), SHA256
`ee363b25e24f12f6a70ee98fe3551ec44accfa7a6346a152ac9abeb2d9ea8d2d`.

The motion-test application was then built and app-only flashed at `0x10000`,
with esptool hash verification. Its binary is 326,768 bytes, SHA256
`48c3a55753930c70383833bbc80415c62fb27c9538d065c02a3ee4c669458409`.
The identity-only application binary is retained locally as
`.arduino-temporary/IMU_Bringup.identity-only.bin` outside this directory.
In an 11-second stationary USB-serial capture, 222 samples spanned 11.05 seconds
(20.0 Hz by device timestamps). Representative magnitudes were 0.992–1.005 g;
the displayed gyro samples were near zero with about 1 degree/s X-axis bias.
A later 14.2-second USB-serial capture received 285 samples at 20.0 Hz with no
serial error. AX ranged -0.106 to -0.081 g, AY 0.063 to 0.078 g, AZ 0.984 to
1.001 g, and gyro axes stayed within about 1 degree/s of zero. The owner
confirmed that the movement did not overlap this capture.

During a subsequent owner-timed tilt/rotation, 141 samples over 7.0 seconds
still arrived at 20.0 Hz. AX ranged -0.276 to -0.062 g, AY -0.044 to 0.111 g,
AZ 0.906 to 1.267 g, and GY -26.09 to 22.24 degrees/s. This confirms motion
response. The USB serial port then closed before the planned post-rotation hold,
so gyro settling after stopping was **not verified**. A previous movement attempt
also lost COM7; the owner reported that the cable may have moved and reseated it.
The exact cause of the USB interruption remains unconfirmed. Do not use these
USB-tethered motion attempts as proof of stable wearable operation.

## External RGB channel diagnostic

With the converter connector unplugged, JP1 cap off, and the RGB module correctly
fitted in J5, send `r` at 115200 baud to drive the red-labelled GPIO1 alone for
ten seconds, or `g` to drive the green-labelled GPIO0 alone. Send `o` to turn
both off early. The other RGB pins and buzzer (GPIO10) remain LOW. All outputs
default to off at boot and turn off automatically after ten seconds. The
red/green source labels now reflect observed colours, not the original handoff.
Send `s` for one red, green, blue sequence (three seconds per channel), then all
off. This sequence uses GPIO1, GPIO0, and GPIO3 respectively.

On 2026-10-17, the updated application compiled with Arduino-ESP32 3.3.10 and
was app-only flashed at `0x10000` through COM7; esptool verified the image hash.
Binary: `.arduino-temporary/IMU_Bringup.red-test.bin`, 327,088 bytes, SHA256
`42e406444271b13aa5b4e66138aa5943f862e8a251ecd575adb9fa008dac379a`.
The serial command returned `RED_ON for 10 seconds` and `RED_OFF timeout`.
The owner observed **green**, not red, from GPIO0. This conflicts with the
handoff's colour labels. No remapping had been made at that point.

The GPIO1 test image was then built and app-only flashed with hash verification:
`.arduino-temporary/IMU_Bringup.gpio1-test.bin`, 327,168 bytes, SHA256
`0d544bed0fdd83d818957bba5a87f3c7f7aa2ef57105845111a9618c9dc989af`.
Its `g` command returned `GPIO1_ON for 10 seconds` and `RGB_OFF timeout`.
The owner observed **red** from GPIO1. The source mapping was then corrected to
red=GPIO1 and green=GPIO0. GPIO3 remains the handoff-reported blue channel,
without direct light-up evidence. At that point, the flashed image still used
the older label mapping; the corrected source had not yet been flashed.
The corrected source compiled with Arduino-ESP32 3.3.10; its retained binary is
`.arduino-temporary/IMU_Bringup.rgb-corrected.bin`, SHA256
`bdc83d6417f1597529ecd3b411e10f549731a9ee49d42918744e2884a2d0f88a`.

The sequence diagnostic was then compiled and app-only flashed at `0x10000`;
esptool verified the written hash. Binary:
`.arduino-temporary/IMU_Bringup.rgb-sequence.bin`, 327,504 bytes, SHA256
`28625444cf6e8b40c5c7bf419404cb1e05ee7d422fff572899cd726f96ecd43e`.
One serial-triggered run reported `SEQ_RED GPIO1`, `SEQ_GREEN GPIO0`,
`SEQ_BLUE GPIO3`, and `SEQ_DONE_ALL_OFF` in order. Physical colour observation
for the complete sequence is still pending; serial output alone does not prove
the LED colours.

## External buzzer diagnostic

The owner confirmed the active buzzer's positive lead at J6.1 (+5 V), negative
lead at J6.3 (Q7 switched return), J6.2 unused, converter unplugged, and JP1
cap off. With USB as the only power source, send `b` at 115200 baud for two
700 ms GPIO10 HIGH pulses separated by a 400 ms LOW gap. Send `o` to force
all RGB and buzzer outputs LOW. The buzzer defaults to LOW at boot and is
automatically turned off after the second pulse.

The 2026-10-17 buzzer diagnostic compiled with Arduino-ESP32 3.3.10 and was
app-only flashed at `0x10000`; esptool verified the written hash. Binary:
`.arduino-temporary/IMU_Bringup.buzzer-test.bin`, 327,840 bytes, SHA256
`30d47fb20a14269042d9f75e2cbd5e8bc96930be4b33a5f0cf6f07bb314a6cf4`.
One serial-triggered run reported both `BUZZER_ON` pulses, the intervening
`BUZZER_OFF gap`, and `BUZZER_DONE_OFF`. The owner heard no sound on the first
USB-powered run. A later replay was serial-confirmed, but no audible result
was reported. Serial logs alone do not prove acoustic output.

## Automatic external-power actuator test

`Actuator_Power_Test/Actuator_Power_Test.ino` is a separate temporary sketch.
It starts without a serial command and repeats red (GPIO1) for 2 s, green
(GPIO0) for 2 s, blue (GPIO3) for 2 s, then all RGB off for 1 s. The active
buzzer control GPIO10 is HIGH for the first 500 ms of each red phase and LOW
otherwise. All pins are initialized LOW before the loop starts. The test runs
until power is removed; it does not read the IMU or advertise over BLE.

The sketch compiled with Arduino-ESP32 3.3.10 and was app-only flashed at
`0x10000` through COM7. Esptool verified the written image. The retained
299,728-byte binary is `.arduino-temporary/Actuator_Power_Test.auto.bin`,
SHA256 `4524064988b974514950327478b8eb67b823251dabbc0552143456c89c5f3efc`.
A short USB serial capture showed green, blue, off, red, and `BUZZER_OFF` as
the sequence repeated without a command. This verifies firmware scheduling,
not externally powered buzzer sound.

For the external-power observation, remove ESP USB **before** connecting the
converter-to-PCB connector. Keep JP1 cap OFF. Use the already documented final
SYS_5V/SYS_GND input pair and correct polarity; never combine ESP USB and the
external converter supply. Switch power on, observe at least one full 7 s
cycle, then switch it off. External power, audible buzzer output, and USB-to-
external-power transition were initially unverified. After following these
instructions, the owner reported that the automatic colour loop and buzzer
were working on external power. This is owner-observed functional evidence,
not a measured supply-voltage/current or endurance result. The ESP remains
flashed with this temporary actuator-only image.
