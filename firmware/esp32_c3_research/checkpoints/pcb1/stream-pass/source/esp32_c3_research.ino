/*
 * Digital Spotter ESP32-C3 — staged Arduino BLE research firmware
 *
 * Purpose:
 *   PCB1 preserves the R9 BLE/status/control/MPU6500 behavior on the assembled
 *   PCB, with external PWM RGB and a timed active-buzzer driver.
 *
 * Security:
 *   Test firmware only. No pairing, bonding, encrypted characteristic permissions,
 *   provisioning, Wi-Fi, MQTT, or application authentication. Raw MPU6500 values
 *   are not calibrated and must not be interpreted as body-frame values, barbell
 *   velocity, power, or production model inputs.
 *
 * Hardware:
 *   MPU6500 SDA18/SCL19, RGB red1/green0/blue3, active buzzer control10.
 *
 * Arduino libraries:
 *   - ESP32 board package by Espressif Systems (provides BLEDevice.h)
 */

#include <Arduino.h>
#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <Wire.h>
#include "board_config.h"

#if !defined(CONFIG_IDF_TARGET_ESP32C3)
#error "Select an ESP32-C3 target."
#endif
#if defined(ARDUINO_USB_CDC_ON_BOOT) && ARDUINO_USB_CDC_ON_BOOT
#error "Disable native USB CDC: GPIO18/19 are wired to IMU I2C. Use USB-UART."
#endif

#ifndef DS_ENABLE_ACTUATOR_CUES
#define DS_ENABLE_ACTUATOR_CUES 1
#endif

// BLE contract used by the matching Raspberry Pi test.
constexpr char DEVICE_NAME[] = "ESP32-C3-Test";
constexpr char SERVICE_UUID[] = "4fafc201-1fb5-459e-8fcc-c5c9c331914b";
constexpr char DEVICE_INFO_CHARACTERISTIC_UUID[] =
    "e193acb8-25ef-422c-b3e5-972eae75b8ea";
constexpr char CONTROL_CHARACTERISTIC_UUID[] =
    "7f725422-d560-4852-96d8-3407f417b1d8";
constexpr char STREAM_CHARACTERISTIC_UUID[] =
    "772af3c3-f1f9-43b0-8230-4dff401446ea";
constexpr char STATUS_CHARACTERISTIC_UUID[] =
    "7f07eb06-7be4-49a1-b952-1ed033b0dfc7";
constexpr char FIRMWARE_VERSION[] = "0.9.1-pcb1";
constexpr char DEVICE_INFO_VALUE[] =
    "protocol=1;firmware=0.9.1-pcb1;hardware=esp32-c3;imu=mpu6500;rate_hz=50";
constexpr char CONTROL_INITIAL_VALUE[] = "ready";
constexpr size_t CONTROL_MAX_REQUEST_BYTES = 48;
constexpr size_t STATUS_MAX_VALUE_BYTES = 96;

constexpr uint8_t RGB_PINS[] = {
    WearablePcbPins::RGB_RED, WearablePcbPins::RGB_GREEN, WearablePcbPins::RGB_BLUE
};
constexpr uint32_t RGB_PWM_FREQUENCY_HZ = 5000;
constexpr uint8_t RGB_PWM_RESOLUTION = 8;
constexpr uint8_t PCB_RGB_BRIGHTNESS = 96;
constexpr uint8_t BUZZER_PIN = WearablePcbPins::BUZZER;
constexpr uint32_t BUZZER_TEST_DURATION_MS = 500;
constexpr uint32_t IDENTIFY_DURATION_MS = 900;
constexpr uint32_t BOOT_CUE_DURATION_MS = 800;
constexpr uint32_t CUE_TEST_STEP_DURATION_MS = 900;
constexpr uint8_t CUE_TEST_STEP_COUNT = 6;
constexpr bool ACTUATOR_CUES_ENABLED = DS_ENABLE_ACTUATOR_CUES != 0;

// Verified wearable I2C contract. R5 accepts only the exact MPU6500 identity.
constexpr uint8_t IMU_SDA_PIN = WearablePcbPins::IMU_SDA;
constexpr uint8_t IMU_SCL_PIN = WearablePcbPins::IMU_SCL;
constexpr uint32_t IMU_I2C_CLOCK_HZ = 100000;
constexpr uint8_t IMU_I2C_ADDRESS = 0x68;
constexpr uint8_t IMU_WHO_AM_I_REGISTER = 0x75;
constexpr uint8_t IMU_WHO_AM_I_VALUE = 0x70;
constexpr uint8_t IMU_SAMPLE_START_REGISTER = 0x3B;
constexpr uint8_t IMU_POWER_MANAGEMENT_REGISTER = 0x6B;
constexpr uint8_t IMU_POWER_MANAGEMENT_2_REGISTER = 0x6C;
constexpr uint8_t IMU_CONFIG_REGISTER = 0x1A;
constexpr uint8_t IMU_SAMPLE_RATE_DIVIDER_REGISTER = 0x19;
constexpr uint8_t IMU_GYROSCOPE_CONFIG_REGISTER = 0x1B;
constexpr uint8_t IMU_ACCELEROMETER_CONFIG_REGISTER = 0x1C;
constexpr uint8_t IMU_TRANSACTION_ATTEMPTS = 3;
constexpr uint8_t IMU_INITIALIZATION_ATTEMPTS = 5;
constexpr uint32_t IMU_INITIALIZATION_RETRY_MS = 100;
constexpr uint32_t IMU_RETRY_DELAY_MS = 2;
constexpr uint32_t IMU_SAMPLE_INTERVAL_US = 20000;
constexpr uint32_t IMU_STATUS_INTERVAL_MS = 5000;
constexpr uint16_t IMU_SERIAL_CAPTURE_SAMPLES = 200;

constexpr uint8_t STREAM_PROTOCOL_VERSION = 1;
constexpr uint8_t STREAM_FLAGS_NONE = 0;
constexpr uint8_t STREAM_FLAG_SENSOR_ERROR = 1U << 3;
constexpr size_t STREAM_PACKET_SIZE = 20;
constexpr uint32_t STREAM_INTERVAL_US = 20000;
constexpr uint32_t STREAM_LOG_INTERVAL_SAMPLES = 50;
constexpr uint32_t STREAM_MAX_SAMPLE_AGE_US = 60000;
constexpr uint32_t ADVERTISING_RESTART_DELAY_MS = 100;
constexpr uint32_t ADVERTISING_RETRY_DELAY_MS = 500;
constexpr uint8_t ADVERTISING_MAX_START_ATTEMPTS = 3;

bool rgbReady = false;
bool buzzerActive = false;
uint32_t buzzerUntilMs = 0;

BLEServer *bleServer = nullptr;
BLECharacteristic *deviceInfoCharacteristic = nullptr;
BLECharacteristic *controlCharacteristic = nullptr;
BLECharacteristic *streamCharacteristic = nullptr;
BLECharacteristic *statusCharacteristic = nullptr;

volatile bool clientConnected = false;
volatile bool restartAdvertising = false;
volatile bool resetStreamSchedule = true;
volatile bool streamEnabled = false;
volatile bool identifyRequested = false;
volatile bool buzzerTestRequested = false;
volatile bool cueTestRequested = false;
bool advertisingConfigured = false;
bool advertisingRestartPending = false;
uint8_t advertisingStartAttempts = 0;
uint32_t nextAdvertisingAttemptMs = 0;
uint32_t advertisingRestartFailureCount = 0;

enum class LedEvent : uint8_t {
  NONE,
  READ,
  WRITE,
  NOTIFY,
  DISCONNECTED,
};

enum class DeviceCue : uint8_t {
  BOOT,
  ADVERTISING,
  CONNECTED,
  STREAMING,
  DISCONNECTED,
  ERROR,
};

volatile LedEvent pendingLedEvent = LedEvent::NONE;

bool streamScheduleActive = false;
uint32_t nextStreamSampleUs = 0;
uint16_t streamSequence = 0;
uint32_t streamNotificationCount = 0;
uint32_t transientColor = 0;
uint32_t transientUntilMs = 0;
uint32_t displayedColor = UINT32_MAX;
uint32_t identifyUntilMs = 0;
uint32_t bootUntilMs = 0;
bool cueTestActive = false;
uint32_t cueTestStartedAtMs = 0;
uint8_t cueTestLastStep = UINT8_MAX;
uint32_t totalStreamNotificationCount = 0;
volatile uint32_t deferredRealtimeLogCount = 0;

struct Mpu6500RawSample {
  int16_t accelerationX;
  int16_t accelerationY;
  int16_t accelerationZ;
  int16_t gyroscopeX;
  int16_t gyroscopeY;
  int16_t gyroscopeZ;
};

bool imuReady = false;
uint8_t imuIdentity = 0;
uint32_t imuNextSampleUs = 0;
uint32_t imuLastStatusMs = 0;
uint32_t imuSampleCount = 0;
uint32_t imuRetryCount = 0;
uint32_t imuErrorCount = 0;
uint32_t imuBusFailureCount = 0;
uint32_t imuConsecutiveErrorCount = 0;
uint16_t imuCaptureRemaining = 0;
uint16_t imuCaptureWritten = 0;
Mpu6500RawSample latestImuSample = {};
bool imuSampleAvailable = false;
uint32_t imuLastSampleUs = 0;
uint32_t lastStreamImuSampleCount = UINT32_MAX;
uint32_t streamSensorSkipCount = 0;

int16_t readBigEndian16(const uint8_t *source) {
  return static_cast<int16_t>(
      (static_cast<uint16_t>(source[0]) << 8) |
      static_cast<uint16_t>(source[1])
  );
}

void clearWireReceiveBuffer() {
  while (Wire.available() > 0) {
    (void)Wire.read();
  }
}

bool readImuRegisters(uint8_t startRegister, uint8_t *output, size_t length) {
  for (uint8_t attempt = 0; attempt < IMU_TRANSACTION_ATTEMPTS; attempt++) {
    Wire.beginTransmission(IMU_I2C_ADDRESS);
    Wire.write(startRegister);
    const uint8_t transmitResult = Wire.endTransmission(false);

    if (transmitResult == 0) {
      const size_t received = Wire.requestFrom(
          static_cast<uint8_t>(IMU_I2C_ADDRESS),
          length,
          true
      );
      if (received == length) {
        for (size_t index = 0; index < length; index++) {
          output[index] = static_cast<uint8_t>(Wire.read());
        }
        return true;
      }
      clearWireReceiveBuffer();
    }

    imuBusFailureCount++;
    if (attempt + 1 < IMU_TRANSACTION_ATTEMPTS) {
      imuRetryCount++;
      delay(IMU_RETRY_DELAY_MS);
    }
  }

  imuErrorCount++;
  return false;
}

bool writeImuRegister(uint8_t targetRegister, uint8_t value) {
  for (uint8_t attempt = 0; attempt < IMU_TRANSACTION_ATTEMPTS; attempt++) {
    Wire.beginTransmission(IMU_I2C_ADDRESS);
    Wire.write(targetRegister);
    Wire.write(value);
    const uint8_t transmitResult = Wire.endTransmission(true);
    if (transmitResult == 0) {
      return true;
    }

    imuBusFailureCount++;
    if (attempt + 1 < IMU_TRANSACTION_ATTEMPTS) {
      imuRetryCount++;
      delay(IMU_RETRY_DELAY_MS);
    }
  }

  imuErrorCount++;
  return false;
}

void printImuStatus() {
  Serial.printf(
      "[IMU_STATUS] ready=%u address=0x%02X who_am_i=0x%02X "
      "rate_hz=50 accel_range_g=2 gyro_range_dps=250 dlpf=3 "
      "samples=%lu retries=%lu errors=%lu bus_failures=%lu "
      "consecutive_errors=%lu ble_payload=real_mpu6500\n",
      imuReady ? 1U : 0U,
      IMU_I2C_ADDRESS,
      imuIdentity,
      static_cast<unsigned long>(imuSampleCount),
      static_cast<unsigned long>(imuRetryCount),
      static_cast<unsigned long>(imuErrorCount),
      static_cast<unsigned long>(imuBusFailureCount),
      static_cast<unsigned long>(imuConsecutiveErrorCount)
  );
}

bool initializeMpu6500() {
  Serial.printf(
      "[IMU] I2C start SDA=GPIO%u SCL=GPIO%u clock_hz=%lu address=0x%02X\n",
      IMU_SDA_PIN,
      IMU_SCL_PIN,
      static_cast<unsigned long>(IMU_I2C_CLOCK_HZ),
      IMU_I2C_ADDRESS
  );

  if (!Wire.begin(IMU_SDA_PIN, IMU_SCL_PIN, IMU_I2C_CLOCK_HZ)) {
    imuErrorCount++;
    Serial.println("[IMU] FAIL Wire.begin returned false");
    return false;
  }

  delay(100);
  bool identityRead = false;
  for (uint8_t attempt = 0; attempt < IMU_INITIALIZATION_ATTEMPTS; attempt++) {
    if (readImuRegisters(IMU_WHO_AM_I_REGISTER, &imuIdentity, 1)) {
      identityRead = true;
      break;
    }
    if (attempt + 1 < IMU_INITIALIZATION_ATTEMPTS) {
      delay(IMU_INITIALIZATION_RETRY_MS);
    }
  }

  if (!identityRead) {
    Serial.println("[IMU] FAIL no WHO_AM_I response at 0x68");
    return false;
  }
  if (imuIdentity != IMU_WHO_AM_I_VALUE) {
    Serial.printf(
        "[IMU] FAIL WHO_AM_I=0x%02X expected=0x%02X\n",
        imuIdentity,
        IMU_WHO_AM_I_VALUE
    );
    return false;
  }

  Serial.println("[IMU] WHO_AM_I=0x70 exact MPU6500 identity PASS");

  const struct {
    uint8_t targetRegister;
    uint8_t value;
    const char *name;
  } settings[] = {
      {IMU_POWER_MANAGEMENT_REGISTER, 0x01, "wake_clock"},
      {IMU_POWER_MANAGEMENT_2_REGISTER, 0x00, "enable_axes"},
      {IMU_CONFIG_REGISTER, 0x03, "dlpf"},
      {IMU_SAMPLE_RATE_DIVIDER_REGISTER, 19, "sample_rate"},
      {IMU_GYROSCOPE_CONFIG_REGISTER, 0x00, "gyro_range"},
      {IMU_ACCELEROMETER_CONFIG_REGISTER, 0x00, "accel_range"},
  };

  for (const auto &setting : settings) {
    if (!writeImuRegister(setting.targetRegister, setting.value)) {
      Serial.printf(
          "[IMU] FAIL configuration=%s register=0x%02X value=0x%02X\n",
          setting.name,
          setting.targetRegister,
          setting.value
      );
      return false;
    }
    uint8_t actual = 0;
    if (!readImuRegisters(setting.targetRegister, &actual, 1) || actual != setting.value) {
      Serial.printf("[IMU] FAIL readback=%s expected=0x%02X actual=0x%02X\n",
                    setting.name, setting.value, actual);
      return false;
    }
    Serial.printf("[IMU] verified %s=0x%02X\n", setting.name, actual);
  }

  Serial.println(
      "[IMU] profile rate=50Hz accel=+/-2g gyro=+/-250dps DLPF=3"
  );
  Serial.println("[IMU] BLE stream uses real MPU6500 raw samples");
  return true;
}

bool readMpu6500Sample(Mpu6500RawSample &sample) {
  uint8_t raw[14] = {};
  if (!readImuRegisters(IMU_SAMPLE_START_REGISTER, raw, sizeof(raw))) {
    imuConsecutiveErrorCount++;
    return false;
  }

  sample.accelerationX = readBigEndian16(raw + 0);
  sample.accelerationY = readBigEndian16(raw + 2);
  sample.accelerationZ = readBigEndian16(raw + 4);
  sample.gyroscopeX = readBigEndian16(raw + 8);
  sample.gyroscopeY = readBigEndian16(raw + 10);
  sample.gyroscopeZ = readBigEndian16(raw + 12);
  imuConsecutiveErrorCount = 0;
  return true;
}

void printImuSampleForCapture(const Mpu6500RawSample &sample) {
  imuCaptureWritten++;
  Serial.printf(
      "[IMU_SAMPLE] capture=%u sample=%lu ax=%d ay=%d az=%d gx=%d gy=%d gz=%d "
      "retries=%lu errors=%lu\n",
      static_cast<unsigned int>(imuCaptureWritten),
      static_cast<unsigned long>(imuSampleCount),
      sample.accelerationX,
      sample.accelerationY,
      sample.accelerationZ,
      sample.gyroscopeX,
      sample.gyroscopeY,
      sample.gyroscopeZ,
      static_cast<unsigned long>(imuRetryCount),
      static_cast<unsigned long>(imuErrorCount)
  );

  if (imuCaptureRemaining > 0) {
    imuCaptureRemaining--;
  }
  if (imuCaptureRemaining == 0) {
    Serial.printf(
        "[IMU_CAPTURE] complete samples=%u retries=%lu errors=%lu\n",
        static_cast<unsigned int>(imuCaptureWritten),
        static_cast<unsigned long>(imuRetryCount),
        static_cast<unsigned long>(imuErrorCount)
    );
  }
}

void handleSerialDiagnosticCommand() {
  if (Serial.available() <= 0) {
    return;
  }

  String command = Serial.readStringUntil('\n');
  command.trim();
  if (command == "status") {
    printImuStatus();
    return;
  }
  if (command == "capture" || command == "capture 200") {
    if (!imuReady) {
      Serial.println("[IMU_CAPTURE] rejected reason=imu_not_ready");
      return;
    }
    imuCaptureRemaining = IMU_SERIAL_CAPTURE_SAMPLES;
    imuCaptureWritten = 0;
    Serial.printf(
        "[IMU_CAPTURE] started requested=%u\n",
        static_cast<unsigned int>(IMU_SERIAL_CAPTURE_SAMPLES)
    );
    return;
  }
  if (command.length() > 0) {
    Serial.printf("[SERIAL] unknown_command=%s\n", command.c_str());
  }
}

void serviceMpu6500() {
  if (!imuReady) {
    return;
  }

  const uint32_t nowUs = micros();
  if (static_cast<int32_t>(nowUs - imuNextSampleUs) < 0) {
    return;
  }
  imuNextSampleUs += IMU_SAMPLE_INTERVAL_US;

  if (!readMpu6500Sample(latestImuSample)) {
    Serial.printf(
        "[IMU_ERROR] sample_failed errors=%lu consecutive=%lu retries=%lu\n",
        static_cast<unsigned long>(imuErrorCount),
        static_cast<unsigned long>(imuConsecutiveErrorCount),
        static_cast<unsigned long>(imuRetryCount)
    );
    return;
  }

  imuSampleCount++;
  imuLastSampleUs = micros();
  imuSampleAvailable = true;
  if (imuCaptureRemaining > 0) {
    printImuSampleForCapture(latestImuSample);
  }
}

bool realtimeStreamActive() {
  return clientConnected && streamEnabled;
}

void deferRealtimeLog() {
  deferredRealtimeLogCount++;
}

constexpr uint32_t rgbColor(uint8_t red, uint8_t green, uint8_t blue) {
  return (static_cast<uint32_t>(red) << 16) |
         (static_cast<uint32_t>(green) << 8) | blue;
}

void showColor(uint32_t color) {
  if (!ACTUATOR_CUES_ENABLED || !rgbReady) {
    return;
  }

  if (color == displayedColor) {
    return;
  }

  for (uint8_t index = 0; index < 3; ++index) {
    const uint8_t channel = (color >> (16 - 8 * index)) & 0xFF;
    ledcWrite(RGB_PINS[index], (channel * PCB_RGB_BRIGHTNESS + 127U) / 255U);
  }
  displayedColor = color;
}

void queueLedEvent(LedEvent event) {
  if (!ACTUATOR_CUES_ENABLED) {
    return;
  }
  pendingLedEvent = event;
}

const char *cueName(DeviceCue cue) {
  switch (cue) {
    case DeviceCue::BOOT:
      return "boot";
    case DeviceCue::ADVERTISING:
      return "advertising";
    case DeviceCue::CONNECTED:
      return "connected";
    case DeviceCue::STREAMING:
      return "streaming";
    case DeviceCue::DISCONNECTED:
      return "disconnected";
    case DeviceCue::ERROR:
      return "error";
  }
  return "unknown";
}

uint32_t cueColor(DeviceCue cue) {
  switch (cue) {
    case DeviceCue::BOOT:
      return rgbColor(180, 180, 180);  // White
    case DeviceCue::ADVERTISING:
      return rgbColor(0, 0, 180);      // Blue
    case DeviceCue::CONNECTED:
      return rgbColor(0, 180, 0);      // Green
    case DeviceCue::STREAMING:
      return rgbColor(0, 180, 255);    // Cyan
    case DeviceCue::DISCONNECTED:
      return rgbColor(255, 60, 0);     // Orange
    case DeviceCue::ERROR:
      return rgbColor(255, 0, 0);      // Red
  }
  return 0;
}

DeviceCue cueForTestStep(uint8_t step) {
  static constexpr DeviceCue sequence[CUE_TEST_STEP_COUNT] = {
      DeviceCue::BOOT,
      DeviceCue::ADVERTISING,
      DeviceCue::CONNECTED,
      DeviceCue::STREAMING,
      DeviceCue::DISCONNECTED,
      DeviceCue::ERROR,
  };
  return sequence[step];
}

void startCueTest() {
  cueTestActive = true;
  cueTestStartedAtMs = millis();
  cueTestLastStep = UINT8_MAX;
  Serial.printf(
      "[ACTUATOR] Cue test started steps=%u step_duration_ms=%lu\n",
      static_cast<unsigned int>(CUE_TEST_STEP_COUNT),
      static_cast<unsigned long>(CUE_TEST_STEP_DURATION_MS)
  );
}

void updateStatusLed() {
  if (!ACTUATOR_CUES_ENABLED) {
    return;
  }

  const uint32_t now = millis();

  if (!imuReady || imuErrorCount > 0) {
    cueTestActive = false;
    pendingLedEvent = LedEvent::NONE;
    showColor(cueColor(DeviceCue::ERROR));
    return;
  }

  // Keep the streaming colour steady; PWM runs in hardware without per-packet
  // output work in the 50 Hz MPU6500 schedule.
  if (clientConnected && streamEnabled) {
    if (cueTestActive) {
      cueTestActive = false;
      Serial.println("[ACTUATOR] Cue test cancelled: stream started");
    }
    pendingLedEvent = LedEvent::NONE;
    showColor(cueColor(DeviceCue::STREAMING));
    return;
  }

  if (!clientConnected && cueTestActive) {
    cueTestActive = false;
    Serial.println("[ACTUATOR] Cue test cancelled: client disconnected");
  }

  if (cueTestActive) {
    const uint32_t elapsedMs = now - cueTestStartedAtMs;
    const uint8_t step = static_cast<uint8_t>(
        elapsedMs / CUE_TEST_STEP_DURATION_MS
    );
    if (step >= CUE_TEST_STEP_COUNT) {
      cueTestActive = false;
      cueTestLastStep = UINT8_MAX;
      Serial.println("[ACTUATOR] Cue test complete");
    } else {
      const DeviceCue cue = cueForTestStep(step);
      if (step != cueTestLastStep) {
        cueTestLastStep = step;
        Serial.printf(
            "[ACTUATOR] Cue test step=%u cue=%s\n",
            static_cast<unsigned int>(step + 1),
            cueName(cue)
        );
      }
      showColor(cueColor(cue));
      return;
    }
  }

  if (now < bootUntilMs) {
    showColor(cueColor(DeviceCue::BOOT));
    return;
  }

  const LedEvent event = pendingLedEvent;

  if (event != LedEvent::NONE) {
    pendingLedEvent = LedEvent::NONE;

    switch (event) {
      case LedEvent::READ:
        transientColor = rgbColor(255, 160, 0);  // Amber
        transientUntilMs = now + 180;
        break;
      case LedEvent::WRITE:
        transientColor = rgbColor(255, 0, 180);  // Magenta
        transientUntilMs = now + 300;
        break;
      case LedEvent::NOTIFY:
        transientColor = rgbColor(0, 180, 255);  // Cyan
        transientUntilMs = now + 120;
        break;
      case LedEvent::DISCONNECTED:
        transientColor = cueColor(DeviceCue::DISCONNECTED);
        transientUntilMs = now + 500;
        break;
      default:
        break;
    }
  }

  if (now < identifyUntilMs) {
    showColor(rgbColor(180, 180, 180));  // White: manual identify.
    return;
  }

  if (now < transientUntilMs) {
    showColor(transientColor);
    return;
  }

  if (clientConnected) {
    showColor(cueColor(DeviceCue::CONNECTED));
    return;
  }

  // Non-blocking blue breathing effect: advertising and waiting for the Pi.
  const uint16_t phase = now % 1600;
  const uint8_t level = phase < 800
      ? 8 + static_cast<uint8_t>(phase / 20)
      : 8 + static_cast<uint8_t>((1600 - phase) / 20);
  showColor(rgbColor(0, 0, level));
}

class TestServerCallbacks : public BLEServerCallbacks {
 public:
  void onConnect(BLEServer *server) override {
    clientConnected = true;
    restartAdvertising = false;
    resetStreamSchedule = true;
    streamEnabled = false;

    Serial.println();
    Serial.println("[BLE] CLIENT CONNECTED");
    Serial.printf("[BLE] Connected clients: %u\n", server->getConnectedCount());
    Serial.println("[BLE] Link security requested by firmware: none");
    Serial.println("[LED] Solid green = connected");
  }

  void onDisconnect(BLEServer *server) override {
    (void)server;
    clientConnected = false;
    restartAdvertising = true;
    resetStreamSchedule = true;
    streamEnabled = false;
    queueLedEvent(LedEvent::DISCONNECTED);

    Serial.println();
    Serial.println("[BLE] CLIENT DISCONNECTED");
    Serial.println("[BLE] Advertising restart queued");
    Serial.println("[LED] Orange flash, then blue breathing = advertising");
  }
};

void writeLittleEndian16(uint8_t *destination, uint16_t value) {
  destination[0] = static_cast<uint8_t>(value & 0xff);
  destination[1] = static_cast<uint8_t>((value >> 8) & 0xff);
}

void writeLittleEndian32(uint8_t *destination, uint32_t value) {
  destination[0] = static_cast<uint8_t>(value & 0xff);
  destination[1] = static_cast<uint8_t>((value >> 8) & 0xff);
  destination[2] = static_cast<uint8_t>((value >> 16) & 0xff);
  destination[3] = static_cast<uint8_t>((value >> 24) & 0xff);
}

void buildRealStreamPacket(
    uint8_t payload[STREAM_PACKET_SIZE],
    uint16_t sequence,
    uint32_t sampleTimeUs,
    uint8_t flags,
    const Mpu6500RawSample &sample
) {
  payload[0] = STREAM_PROTOCOL_VERSION;
  payload[1] = flags;
  writeLittleEndian16(payload + 2, sequence);
  writeLittleEndian32(payload + 4, sampleTimeUs);
  writeLittleEndian16(payload + 8, static_cast<uint16_t>(sample.accelerationX));
  writeLittleEndian16(payload + 10, static_cast<uint16_t>(sample.accelerationY));
  writeLittleEndian16(payload + 12, static_cast<uint16_t>(sample.accelerationZ));
  writeLittleEndian16(payload + 14, static_cast<uint16_t>(sample.gyroscopeX));
  writeLittleEndian16(payload + 16, static_cast<uint16_t>(sample.gyroscopeY));
  writeLittleEndian16(payload + 18, static_cast<uint16_t>(sample.gyroscopeZ));
}

void sendRealStreamSample() {
  const uint16_t sequence = streamSequence;
  streamSequence++;

  const uint32_t nowUs = micros();
  const uint32_t sampleAgeUs = nowUs - imuLastSampleUs;
  if (!imuReady || !imuSampleAvailable ||
      sampleAgeUs > STREAM_MAX_SAMPLE_AGE_US ||
      imuSampleCount == lastStreamImuSampleCount) {
    streamSensorSkipCount++;
    if (streamSensorSkipCount <= 3 || streamSensorSkipCount % 50 == 0) {
      Serial.printf(
          "[STREAM] Real sample skipped sequence=%u ready=%u available=%u "
          "age_us=%lu duplicate=%u skips=%lu\n",
          static_cast<unsigned int>(sequence),
          imuReady ? 1U : 0U,
          imuSampleAvailable ? 1U : 0U,
          static_cast<unsigned long>(sampleAgeUs),
          imuSampleCount == lastStreamImuSampleCount ? 1U : 0U,
          static_cast<unsigned long>(streamSensorSkipCount)
      );
    }
    return;
  }

  const uint8_t flags = imuErrorCount > 0
      ? STREAM_FLAG_SENSOR_ERROR
      : STREAM_FLAGS_NONE;
  uint8_t payload[STREAM_PACKET_SIZE] = {};
  buildRealStreamPacket(
      payload,
      sequence,
      imuLastSampleUs,
      flags,
      latestImuSample
  );
  lastStreamImuSampleCount = imuSampleCount;

  streamCharacteristic->setValue(payload, sizeof(payload));
  streamCharacteristic->notify();

  streamNotificationCount++;
  totalStreamNotificationCount++;
  queueLedEvent(LedEvent::NOTIFY);

  if (streamNotificationCount <= 3 ||
      streamNotificationCount % STREAM_LOG_INTERVAL_SAMPLES == 0) {
    Serial.printf(
        "[GATT] STREAM NOTIFY sample=%lu sequence=%u "
        "sensor_time_us=%lu length=%u source=mpu6500 imu_sample=%lu "
        "age_us=%lu flags=0x%02X i2c_retries=%lu i2c_errors=%lu\n",
        static_cast<unsigned long>(streamNotificationCount),
        static_cast<unsigned int>(sequence),
        static_cast<unsigned long>(imuLastSampleUs),
        static_cast<unsigned int>(sizeof(payload)),
        static_cast<unsigned long>(imuSampleCount),
        static_cast<unsigned long>(sampleAgeUs),
        flags,
        static_cast<unsigned long>(imuRetryCount),
        static_cast<unsigned long>(imuErrorCount)
    );
  }
}

class DeviceInfoCharacteristicCallbacks : public BLECharacteristicCallbacks {
 public:
  void onRead(BLECharacteristic *characteristic) override {
    const auto value = characteristic->getValue();
    if (realtimeStreamActive()) {
      deferRealtimeLog();
      return;
    }
    queueLedEvent(LedEvent::READ);

    Serial.printf(
        "[GATT] DEVICE_INFO READ uuid=%s length=%u value=%s\n",
        DEVICE_INFO_CHARACTERISTIC_UUID,
        static_cast<unsigned int>(value.length()),
        value.c_str()
    );
    Serial.println("[LED] Amber flash = device information read");
  }
};

bool isPrintableControlText(const String &value) {
  if (value.length() == 0 || value.length() > CONTROL_MAX_REQUEST_BYTES) {
    return false;
  }

  for (size_t index = 0; index < value.length(); index++) {
    const uint8_t byte = static_cast<uint8_t>(value[index]);
    if (byte < 0x20 || byte > 0x7e) {
      return false;
    }
  }

  return true;
}

class ControlCharacteristicCallbacks : public BLECharacteristicCallbacks {
 public:
  void onRead(BLECharacteristic *characteristic) override {
    const auto value = characteristic->getValue();
    if (realtimeStreamActive()) {
      deferRealtimeLog();
      return;
    }
    queueLedEvent(LedEvent::READ);

    Serial.printf(
        "[GATT] CONTROL READ uuid=%s length=%u value=%s\n",
        CONTROL_CHARACTERISTIC_UUID,
        static_cast<unsigned int>(value.length()),
        value.c_str()
    );
    Serial.println("[LED] Amber flash = control response read");
  }

  void onWrite(BLECharacteristic *characteristic) override {
    const auto request = characteristic->getValue();
    const bool realtimeAtEntry = realtimeStreamActive();
    if (!realtimeAtEntry) {
      queueLedEvent(LedEvent::WRITE);
    }

    if (request.length() > CONTROL_MAX_REQUEST_BYTES) {
      characteristic->setValue("error:too_long");
      if (realtimeAtEntry) {
        deferRealtimeLog();
      } else {
        Serial.printf(
            "[GATT] CONTROL WRITE rejected=too_long length=%u max=%u\n",
            static_cast<unsigned int>(request.length()),
            static_cast<unsigned int>(CONTROL_MAX_REQUEST_BYTES)
        );
      }
      return;
    }

    if (!isPrintableControlText(request)) {
      characteristic->setValue("error:invalid_text");
      if (realtimeAtEntry) {
        deferRealtimeLog();
      } else {
        Serial.printf(
            "[GATT] CONTROL WRITE rejected=invalid_text length=%u\n",
            static_cast<unsigned int>(request.length())
        );
      }
      return;
    }

    const char *response = "error:unknown_command";
    const char *action = "unknown";
    bool idempotent = false;

    if (request == "stream:start") {
      idempotent = streamEnabled;
      if (!streamEnabled) {
        streamEnabled = true;
        resetStreamSchedule = true;
      }
      response = "ok:streaming";
      action = "stream_start";
    } else if (request == "stream:stop") {
      idempotent = !streamEnabled;
      streamEnabled = false;
      response = "ok:idle";
      action = "stream_stop";
    } else if (request == "identify") {
      identifyRequested = true;
      response = "ok:identify";
      action = "identify";
    } else if (request == "buzzer:test") {
      if (ACTUATOR_CUES_ENABLED) {
        buzzerTestRequested = true;
        response = "ok:buzzer_test";
        action = "buzzer_test";
      } else {
        response = "error:actuators_disabled";
        action = "disabled";
      }
    } else if (request == "cue:test") {
      if (!ACTUATOR_CUES_ENABLED) {
        response = "error:actuators_disabled";
        action = "disabled";
      } else if (streamEnabled) {
        response = "error:busy_streaming";
        action = "cue_test_rejected";
      } else {
        cueTestRequested = true;
        response = "ok:cue_test";
        action = "cue_test";
      }
    }

    characteristic->setValue(response);

    if (realtimeAtEntry || realtimeStreamActive()) {
      deferRealtimeLog();
    } else {
      Serial.printf(
          "[GATT] CONTROL WRITE uuid=%s request=%s response=%s "
          "action=%s idempotent=%u\n",
          CONTROL_CHARACTERISTIC_UUID,
          request.c_str(),
          response,
          action,
          idempotent ? 1U : 0U
      );
      Serial.println("[LED] Magenta flash = control request accepted");
    }
  }
};

const char *researchState() {
  if (!imuReady || imuErrorCount > 0) {
    return "error";
  }
  if (clientConnected && streamEnabled) {
    return "streaming";
  }
  return "idle";
}

class StatusCharacteristicCallbacks : public BLECharacteristicCallbacks {
 public:
  void onRead(BLECharacteristic *characteristic) override {
    char value[STATUS_MAX_VALUE_BYTES] = {};
    const int written = snprintf(
        value,
        sizeof(value),
        "state=%s;i2c_errors=%lu;samples_sent=%lu;uptime_ms=%lu",
        researchState(),
        static_cast<unsigned long>(imuErrorCount),
        static_cast<unsigned long>(totalStreamNotificationCount),
        static_cast<unsigned long>(millis())
    );

    if (written < 0 || static_cast<size_t>(written) >= sizeof(value)) {
      characteristic->setValue(
          "state=error;i2c_errors=0;samples_sent=0;uptime_ms=0"
      );
      Serial.println("[GATT] STATUS READ encoding failed");
      return;
    }

    characteristic->setValue(value);
    if (realtimeStreamActive()) {
      deferRealtimeLog();
    } else {
      queueLedEvent(LedEvent::READ);
      Serial.printf(
          "[GATT] STATUS READ uuid=%s length=%u value=%s\n",
          STATUS_CHARACTERISTIC_UUID,
          static_cast<unsigned int>(written),
          value
      );
    }
  }
};

void configureAdvertising() {
  if (advertisingConfigured) {
    return;
  }

  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(SERVICE_UUID);
  advertising->setScanResponse(true);
  advertisingConfigured = true;
}

bool startAdvertising(const char *reason) {
  configureAdvertising();
  BLEAdvertising *advertising = BLEDevice::getAdvertising();

  if (advertising->isAdvertising()) {
    Serial.printf("[BLE] Advertising already active reason=%s\n", reason);
    return true;
  }

  const bool started = advertising->start();
  if (!started) {
    Serial.printf("[BLE] Advertising start rejected reason=%s\n", reason);
    return false;
  }

  Serial.printf("[BLE] ADVERTISING reason=%s\n", reason);
  Serial.printf("[BLE] Name: %s\n", DEVICE_NAME);
  Serial.printf("[BLE] Address: %s\n", BLEDevice::getAddress().toString().c_str());
  Serial.printf("[BLE] Service UUID: %s\n", SERVICE_UUID);
  Serial.printf(
      "[BLE] Device-info characteristic UUID: %s\n",
      DEVICE_INFO_CHARACTERISTIC_UUID
  );
  Serial.println("[BLE] Device-info characteristic properties: READ only");
  Serial.printf(
      "[BLE] Control characteristic UUID: %s\n",
      CONTROL_CHARACTERISTIC_UUID
  );
  Serial.printf(
      "[BLE] Control properties: READ | WRITE, max request: %u bytes\n",
      static_cast<unsigned int>(CONTROL_MAX_REQUEST_BYTES)
  );
  Serial.printf(
      "[BLE] Stream characteristic UUID: %s\n",
      STREAM_CHARACTERISTIC_UUID
  );
  Serial.println("[BLE] Stream properties: NOTIFY only");
  Serial.printf(
      "[BLE] Status characteristic UUID: %s\n",
      STATUS_CHARACTERISTIC_UUID
  );
  Serial.println("[BLE] Status properties: READ only, bounded ASCII");
  Serial.println("[BLE] Stream payload: 20-byte little-endian real MPU6500 raw data");
  Serial.println("[BLE] Stream rate: 50 Hz; raw values are not calibrated");
  Serial.println("[BLE] Stream control: explicit stream:start / stream:stop");
  Serial.println("[BLE] Pairing/bonding/encrypted permissions: OFF");
  Serial.println("[LED] Blue breathing = waiting for a connection");
  return true;
}

void serviceAdvertisingRestart() {
  const uint32_t nowMs = millis();

  if (restartAdvertising) {
    restartAdvertising = false;
    advertisingRestartPending = true;
    advertisingStartAttempts = 0;
    nextAdvertisingAttemptMs = nowMs + ADVERTISING_RESTART_DELAY_MS;
    Serial.printf(
        "[BLE] Advertising restart scheduled delay_ms=%lu max_attempts=%u\n",
        static_cast<unsigned long>(ADVERTISING_RESTART_DELAY_MS),
        static_cast<unsigned int>(ADVERTISING_MAX_START_ATTEMPTS)
    );
  }

  if (!advertisingRestartPending) {
    return;
  }

  if (clientConnected) {
    advertisingRestartPending = false;
    advertisingStartAttempts = 0;
    Serial.println("[BLE] Advertising restart cancelled: client connected");
    return;
  }

  if (static_cast<int32_t>(nowMs - nextAdvertisingAttemptMs) < 0) {
    return;
  }

  advertisingStartAttempts++;
  Serial.printf(
      "[BLE] Advertising restart attempt=%u/%u\n",
      static_cast<unsigned int>(advertisingStartAttempts),
      static_cast<unsigned int>(ADVERTISING_MAX_START_ATTEMPTS)
  );

  if (startAdvertising("disconnect-recovery")) {
    advertisingRestartPending = false;
    Serial.printf(
        "[BLE] Advertising restart passed attempt=%u\n",
        static_cast<unsigned int>(advertisingStartAttempts)
    );
    return;
  }

  if (advertisingStartAttempts < ADVERTISING_MAX_START_ATTEMPTS) {
    nextAdvertisingAttemptMs = nowMs + ADVERTISING_RETRY_DELAY_MS;
    Serial.printf(
        "[BLE] Advertising retry scheduled delay_ms=%lu\n",
        static_cast<unsigned long>(ADVERTISING_RETRY_DELAY_MS)
    );
    return;
  }

  advertisingRestartPending = false;
  advertisingRestartFailureCount++;
  Serial.printf(
      "[BLE] Advertising restart failed attempts=%u total_failures=%lu\n",
      static_cast<unsigned int>(advertisingStartAttempts),
      static_cast<unsigned long>(advertisingRestartFailureCount)
  );
}

void setup() {
  for (uint8_t pin : RGB_PINS) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
  digitalWrite(BUZZER_PIN, LOW);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);
  Serial.begin(115200);
  delay(1200);

  if (ACTUATOR_CUES_ENABLED) {
    rgbReady = true;
    for (uint8_t pin : RGB_PINS) {
      if (!ledcAttach(pin, RGB_PWM_FREQUENCY_HZ, RGB_PWM_RESOLUTION)) {
        rgbReady = false;
        Serial.printf("[HW] RGB PWM attach failed GPIO%u\n", pin);
      }
    }
  }
  showColor(cueColor(DeviceCue::BOOT));

  Serial.println();
  Serial.println("====================================================");
  Serial.println(" Digital Spotter ESP32-C3 — Assembled PCB BLE");
  Serial.println("====================================================");
  Serial.printf("[HW] Chip: %s revision %u\n", ESP.getChipModel(), ESP.getChipRevision());
  Serial.printf("[HW] CPU: %u MHz\n", ESP.getCpuFreqMHz());
  Serial.printf("[HW] Free heap before BLE: %u bytes\n", ESP.getFreeHeap());
  Serial.printf("[HW] External RGB R=%u G=%u B=%u PWM_ready=%u\n",
                RGB_PINS[0], RGB_PINS[1], RGB_PINS[2], rgbReady ? 1U : 0U);
  Serial.printf("[HW] Active buzzer: GPIO %u, timed HIGH/LOW test only\n", BUZZER_PIN);
  Serial.printf(
      "[HW] Actuator cues: %s (compile-time DS_ENABLE_ACTUATOR_CUES=%u)\n",
      ACTUATOR_CUES_ENABLED ? "enabled" : "disabled",
      ACTUATOR_CUES_ENABLED ? 1U : 0U
  );
  Serial.printf("[FW] Version: %s, protocol: 1\n", FIRMWARE_VERSION);
  Serial.println("[TEST] Wi-Fi/MQTT/security are intentionally not initialized");
  Serial.println("[TEST] PCB1 retains the R9 BLE/data contract on the new PCB");
  Serial.println("[TEST] Raw values are not calibrated or approved model inputs");

  imuReady = initializeMpu6500();
  imuNextSampleUs = micros();
  imuLastStatusMs = millis();
  printImuStatus();

  BLEDevice::init(DEVICE_NAME);

  bleServer = BLEDevice::createServer();
  bleServer->setCallbacks(new TestServerCallbacks());

  BLEService *service = bleServer->createService(SERVICE_UUID);
  deviceInfoCharacteristic = service->createCharacteristic(
      DEVICE_INFO_CHARACTERISTIC_UUID,
      BLECharacteristic::PROPERTY_READ
  );
  deviceInfoCharacteristic->setCallbacks(
      new DeviceInfoCharacteristicCallbacks()
  );
  deviceInfoCharacteristic->setValue(DEVICE_INFO_VALUE);

  controlCharacteristic = service->createCharacteristic(
      CONTROL_CHARACTERISTIC_UUID,
      BLECharacteristic::PROPERTY_READ |
          BLECharacteristic::PROPERTY_WRITE
  );
  controlCharacteristic->setCallbacks(new ControlCharacteristicCallbacks());
  controlCharacteristic->setValue(CONTROL_INITIAL_VALUE);

  statusCharacteristic = service->createCharacteristic(
      STATUS_CHARACTERISTIC_UUID,
      BLECharacteristic::PROPERTY_READ
  );
  statusCharacteristic->setCallbacks(new StatusCharacteristicCallbacks());
  statusCharacteristic->setValue(
      "state=idle;i2c_errors=0;samples_sent=0;uptime_ms=0"
  );

  streamCharacteristic = service->createCharacteristic(
      STREAM_CHARACTERISTIC_UUID,
      BLECharacteristic::PROPERTY_NOTIFY
  );
  streamCharacteristic->addDescriptor(new BLE2902());
  service->start();

  if (!startAdvertising("boot")) {
    restartAdvertising = true;
    Serial.println("[BLE] Initial advertising failed; bounded recovery queued");
  }
  bootUntilMs = millis() + BOOT_CUE_DURATION_MS;
  Serial.printf(
      "[ACTUATOR] Boot cue=white duration_ms=%lu\n",
      static_cast<unsigned long>(BOOT_CUE_DURATION_MS)
  );
  Serial.printf("[HW] Free heap after BLE: %u bytes\n", ESP.getFreeHeap());
  Serial.println("[READY] Open the Pi client and connect to ESP32-C3-Test");
}

void loop() {
  handleSerialDiagnosticCommand();
  serviceMpu6500();

  if (buzzerActive &&
      (!clientConnected || static_cast<int32_t>(millis() - buzzerUntilMs) >= 0)) {
    digitalWrite(BUZZER_PIN, LOW);
    buzzerActive = false;
  }

  if (identifyRequested && (!clientConnected || !streamEnabled)) {
    identifyRequested = false;
    identifyUntilMs = millis() + IDENTIFY_DURATION_MS;
    Serial.printf(
        "[ACTUATOR] Identify LED started duration_ms=%lu\n",
        static_cast<unsigned long>(IDENTIFY_DURATION_MS)
    );
  }

  if (buzzerTestRequested) {
    buzzerTestRequested = false;
    const bool realtimeAtStart = realtimeStreamActive();
    digitalWrite(BUZZER_PIN, HIGH);
    buzzerUntilMs = millis() + BUZZER_TEST_DURATION_MS;
    buzzerActive = true;
    if (realtimeAtStart) {
      deferRealtimeLog();
    } else {
      Serial.printf(
          "[ACTUATOR] Active buzzer HIGH duration_ms=%lu\n",
          static_cast<unsigned long>(BUZZER_TEST_DURATION_MS)
      );
    }
  }

  if (cueTestRequested) {
    cueTestRequested = false;
    if (!clientConnected || streamEnabled) {
      Serial.println("[ACTUATOR] Cue test skipped: requires connected idle state");
    } else {
      startCueTest();
    }
  }

  if (!realtimeStreamActive() && deferredRealtimeLogCount > 0) {
    const uint32_t count = deferredRealtimeLogCount;
    deferredRealtimeLogCount = 0;
    Serial.printf(
        "[REALTIME] Deferred nonessential log events=%lu\n",
        static_cast<unsigned long>(count)
    );
  }

  const uint32_t nowMs = millis();
  if (nowMs - imuLastStatusMs >= IMU_STATUS_INTERVAL_MS) {
    imuLastStatusMs = nowMs;
    // The long serial diagnostic can briefly block the single-core loop when
    // the UART buffer fills. Keep it available while idle, but do not inject
    // periodic jitter into the proven 50 Hz sensor/notification path.
    if (!clientConnected || !streamEnabled) {
      printImuStatus();
    }
  }

  serviceAdvertisingRestart();

  if (!clientConnected || !streamEnabled) {
    streamScheduleActive = false;
  } else {
    const uint32_t nowUs = micros();

    if (resetStreamSchedule || !streamScheduleActive) {
      resetStreamSchedule = false;
      streamScheduleActive = true;
      streamSequence = 0;
      streamNotificationCount = 0;
      streamSensorSkipCount = 0;
      lastStreamImuSampleCount = UINT32_MAX;
      // Align BLE emission to the next sensor boundary. Both schedules retain
      // the proven 20 ms interval, but a notification can no longer run just
      // before the corresponding I2C sample and encounter the previous sample.
      nextStreamSampleUs = imuNextSampleUs;
      Serial.println("[STREAM] Real MPU6500 50 Hz schedule started at sequence 0");
    }

    if (static_cast<int32_t>(nowUs - nextStreamSampleUs) >= 0) {
      nextStreamSampleUs += STREAM_INTERVAL_US;
      // The first loop-level call may have occurred a few microseconds before
      // the shared boundary. Recheck the MPU immediately before notification.
      serviceMpu6500();
      sendRealStreamSample();

      const uint32_t afterNotifyUs = micros();
      if (static_cast<int32_t>(afterNotifyUs - nextStreamSampleUs) >= 0) {
        const uint32_t skippedSamples =
            ((afterNotifyUs - nextStreamSampleUs) / STREAM_INTERVAL_US) + 1;
        nextStreamSampleUs += skippedSamples * STREAM_INTERVAL_US;
        streamSequence = static_cast<uint16_t>(streamSequence + skippedSamples);
        Serial.printf(
            "[STREAM] Scheduler overrun: skipped=%lu next_sequence=%u\n",
            static_cast<unsigned long>(skippedSamples),
            static_cast<unsigned int>(streamSequence)
        );
      }
    }
  }

  updateStatusLed();
  delay(1);
}
