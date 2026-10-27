#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include "pin_config.h"

#if !defined(CONFIG_IDF_TARGET_ESP32C3)
#error "Select an ESP32-C3 target, not the original ESP32 or another family."
#endif
#if defined(ARDUINO_USB_CDC_ON_BOOT) && ARDUINO_USB_CDC_ON_BOOT
#error "Disable native USB CDC on boot: GPIO18/19 are wired to IMU I2C. Use the USB-UART bridge."
#endif

using namespace GymSpotterPins;
static constexpr uint8_t kImuAddress = IMU_EXPECTED_ADDRESS;
static constexpr uint8_t kWhoAmI = 0x75;
static constexpr uint8_t kSampleStart = 0x3B;
static constexpr uint32_t kSampleIntervalMs = 50;
static constexpr float kAccelCountsPerG = 16384.0f; // +/-2 g
static constexpr float kGyroCountsPerDps = 131.0f; // +/-250 deg/s
static bool imuReady = false;
static uint32_t nextSampleMs = 0;
static uint32_t rgbOffAtMs = 0;
static uint8_t activeRgbPin = UINT8_MAX;
static int8_t rgbSequenceStep = -1;
static int8_t buzzerPulsePhase = -1;
static uint32_t buzzerNextMs = 0;
static constexpr uint8_t kRgbSequencePins[] = {RGB_RED, RGB_GREEN, RGB_BLUE};
static const char *const kRgbSequenceNames[] = {"RED", "GREEN", "BLUE"};

static void outputsOff() {
  const uint8_t pins[] = {RGB_RED, RGB_GREEN, RGB_BLUE, BUZZER};
  for (uint8_t p : pins) {
    digitalWrite(p, LOW);
    pinMode(p, OUTPUT);
    digitalWrite(p, LOW);
  }
}

static void allRgbOff() {
  digitalWrite(RGB_RED, RGB_OFF);
  digitalWrite(RGB_GREEN, RGB_OFF);
  digitalWrite(RGB_BLUE, RGB_OFF);
}

static void handleActuatorTest() {
  if (Serial.available() > 0) {
    const int command = Serial.read();
    if (command == 'r' || command == 'g') {
      allRgbOff();
      digitalWrite(BUZZER, BUZZER_OFF);
      buzzerPulsePhase = -1;
      rgbSequenceStep = -1;
      activeRgbPin = command == 'r' ? RGB_RED : RGB_GREEN;
      digitalWrite(activeRgbPin, RGB_ON);
      rgbOffAtMs = millis() + 10000;
      Serial.printf("GPIO%u_ON for 10 seconds\n", activeRgbPin);
    } else if (command == 's') {
      allRgbOff();
      digitalWrite(BUZZER, BUZZER_OFF);
      buzzerPulsePhase = -1;
      rgbSequenceStep = 0;
      activeRgbPin = kRgbSequencePins[rgbSequenceStep];
      digitalWrite(activeRgbPin, RGB_ON);
      rgbOffAtMs = millis() + 3000;
      Serial.printf("SEQ_%s GPIO%u\n", kRgbSequenceNames[rgbSequenceStep], activeRgbPin);
    } else if (command == 'b') {
      allRgbOff();
      activeRgbPin = UINT8_MAX;
      rgbSequenceStep = -1;
      rgbOffAtMs = 0;
      digitalWrite(BUZZER, BUZZER_ON);
      buzzerPulsePhase = 0;
      buzzerNextMs = millis() + 700;
      Serial.printf("BUZZER_ON GPIO%u pulse=1\n", BUZZER);
    } else if (command == 'o') {
      allRgbOff();
      digitalWrite(BUZZER, BUZZER_OFF);
      activeRgbPin = UINT8_MAX;
      rgbSequenceStep = -1;
      rgbOffAtMs = 0;
      buzzerPulsePhase = -1;
      Serial.println("ACTUATORS_OFF");
    }
  }
  if (rgbOffAtMs != 0 && static_cast<int32_t>(millis() - rgbOffAtMs) >= 0) {
    digitalWrite(activeRgbPin, RGB_OFF);
    if (rgbSequenceStep >= 0 && rgbSequenceStep < 2) {
      ++rgbSequenceStep;
      activeRgbPin = kRgbSequencePins[rgbSequenceStep];
      digitalWrite(activeRgbPin, RGB_ON);
      rgbOffAtMs = millis() + 3000;
      Serial.printf("SEQ_%s GPIO%u\n", kRgbSequenceNames[rgbSequenceStep], activeRgbPin);
    } else {
      activeRgbPin = UINT8_MAX;
      rgbOffAtMs = 0;
      if (rgbSequenceStep >= 0) {
        rgbSequenceStep = -1;
        Serial.println("SEQ_DONE_ALL_OFF");
      } else {
        Serial.println("RGB_OFF timeout");
      }
    }
  }
  if (buzzerPulsePhase >= 0 &&
      static_cast<int32_t>(millis() - buzzerNextMs) >= 0) {
    if (buzzerPulsePhase == 0) {
      digitalWrite(BUZZER, BUZZER_OFF);
      buzzerPulsePhase = 1;
      buzzerNextMs = millis() + 400;
      Serial.println("BUZZER_OFF gap");
    } else if (buzzerPulsePhase == 1) {
      digitalWrite(BUZZER, BUZZER_ON);
      buzzerPulsePhase = 2;
      buzzerNextMs = millis() + 700;
      Serial.printf("BUZZER_ON GPIO%u pulse=2\n", BUZZER);
    } else {
      digitalWrite(BUZZER, BUZZER_OFF);
      buzzerPulsePhase = -1;
      buzzerNextMs = 0;
      Serial.println("BUZZER_DONE_OFF");
    }
  }
}

static bool readBytes(uint8_t reg, uint8_t *values, size_t count) {
  Wire.beginTransmission(kImuAddress);
  Wire.write(reg);
  uint8_t error = Wire.endTransmission(false);
  if (error != 0) {
    Serial.printf("READ_REG_ERROR reg=0x%02X status=%u\n", reg, error);
    return false;
  }
  size_t received = Wire.requestFrom(kImuAddress, count, true);
  if (received != count || Wire.available() < static_cast<int>(count)) {
    Serial.printf("SHORT_READ reg=0x%02X expected=%u received=%u\n", reg,
                  static_cast<unsigned>(count), static_cast<unsigned>(received));
    while (Wire.available()) Wire.read();
    return false;
  }
  for (size_t i = 0; i < count; ++i) values[i] = static_cast<uint8_t>(Wire.read());
  return true;
}

static bool writeVerifiedRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(kImuAddress);
  Wire.write(reg);
  Wire.write(value);
  uint8_t error = Wire.endTransmission();
  if (error != 0) {
    Serial.printf("WRITE_REG_ERROR reg=0x%02X status=%u\n", reg, error);
    return false;
  }
  uint8_t actual = 0;
  if (!readBytes(reg, &actual, 1)) return false;
  if (actual != value) {
    Serial.printf("CONFIG_MISMATCH reg=0x%02X expected=0x%02X actual=0x%02X\n",
                  reg, value, actual);
    return false;
  }
  return true;
}

static bool initializeImu() {
  uint8_t identity = 0;
  if (!readBytes(kWhoAmI, &identity, 1)) return false;
  Serial.printf("WHO_AM_I addr=0x%02X value=0x%02X\n", kImuAddress, identity);
  if (identity != 0x70) {
    Serial.println("IMU_ID_MISMATCH: expected MPU6500 0x70; no samples will be printed.");
    return false;
  }

  // Wake all axes and use the X-gyro clock. DLPF=3 gives a 1 kHz base rate;
  // 1 kHz / (1 + 49) = 20 Hz at the sensor data registers.
  if (!writeVerifiedRegister(0x6B, 0x01) ||
      !writeVerifiedRegister(0x6C, 0x00)) return false;
  delay(100);
  if (!writeVerifiedRegister(0x1A, 0x03) ||
      !writeVerifiedRegister(0x19, 49) ||
      !writeVerifiedRegister(0x1B, 0x00) ||
      !writeVerifiedRegister(0x1C, 0x00)) return false;

  Serial.println("MPU6500 awake; all accel/gyro axes enabled; config readback PASS.");
  Serial.println("Accelerometer range: +/-2 g (16384 counts/g).");
  Serial.println("Gyroscope range: +/-250 deg/s (131 counts/(deg/s)).");
  Serial.println("Sensor output and serial read interval: approximately 20 Hz.");
  return true;
}

static int16_t signedWord(const uint8_t *bytes) {
  return static_cast<int16_t>((static_cast<uint16_t>(bytes[0]) << 8) | bytes[1]);
}

static void printSample() {
  uint8_t bytes[14]; // Accel XYZ, temperature, gyro XYZ, all big-endian.
  if (!readBytes(kSampleStart, bytes, sizeof(bytes))) {
    Serial.println("SAMPLE_READ_FAILED");
    return;
  }

  const float ax = signedWord(bytes + 0) / kAccelCountsPerG;
  const float ay = signedWord(bytes + 2) / kAccelCountsPerG;
  const float az = signedWord(bytes + 4) / kAccelCountsPerG;
  const float gx = signedWord(bytes + 8) / kGyroCountsPerDps;
  const float gy = signedWord(bytes + 10) / kGyroCountsPerDps;
  const float gz = signedWord(bytes + 12) / kGyroCountsPerDps;
  const float magnitude = sqrtf(ax * ax + ay * ay + az * az);
  Serial.printf("ms=%lu AX=%.3f AY=%.3f AZ=%.3f g | GX=%.2f GY=%.2f GZ=%.2f dps | MAG=%.3f g\n",
                static_cast<unsigned long>(millis()), ax, ay, az, gx, gy, gz,
                magnitude);
}

void setup() {
  outputsOff();
  Serial.begin(SERIAL_BAUD);
  delay(1500);
  Serial.println("Gym Spotter assembled-PCB MPU6500 motion test");
  Serial.printf("SDA=%u SCL=%u I2C=%luHz RGB=%u/%u/%u BUZZER=%u\n",
                IMU_SDA, IMU_SCL, static_cast<unsigned long>(I2C_HZ),
                RGB_RED, RGB_GREEN, RGB_BLUE, BUZZER);
  Serial.printf("Send 's' for RGB sequence; 'r'=GPIO%u, 'g'=GPIO%u, 'b'=buzzer, 'o'=off.\n",
                RGB_RED, RGB_GREEN);
  const bool busReady = Wire.begin(IMU_SDA, IMU_SCL, I2C_HZ);
  Wire.setTimeOut(50);
  if (!busReady) {
    Serial.println("I2C_BEGIN_FAILED");
    return;
  }
  imuReady = initializeImu();
  if (imuReady) nextSampleMs = millis();
}

void loop() {
  handleActuatorTest();
  if (!imuReady) {
    delay(10);
    return;
  }
  const uint32_t now = millis();
  if (static_cast<int32_t>(now - nextSampleMs) < 0) {
    delay(1);
    return;
  }
  nextSampleMs += kSampleIntervalMs;
  if (static_cast<int32_t>(now - nextSampleMs) >= 0) {
    nextSampleMs = now + kSampleIntervalMs; // Skip missed slots; no catch-up burst.
  }
  printSample();
}
