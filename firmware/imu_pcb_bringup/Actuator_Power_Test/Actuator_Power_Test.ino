#include <Arduino.h>
#include "../IMU_Bringup/pin_config.h"

#if !defined(CONFIG_IDF_TARGET_ESP32C3)
#error "Select an ESP32-C3 target."
#endif
#if defined(ARDUINO_USB_CDC_ON_BOOT) && ARDUINO_USB_CDC_ON_BOOT
#error "Disable native USB CDC: GPIO18/19 are wired to the IMU on this PCB."
#endif

using namespace GymSpotterPins;

static constexpr uint8_t kLedPins[] = {RGB_RED, RGB_GREEN, RGB_BLUE};
static const char *const kPhaseNames[] = {"RED", "GREEN", "BLUE", "OFF"};
static constexpr uint32_t kPhaseMs[] = {2000, 2000, 2000, 1000};
static constexpr uint32_t kBuzzerPulseMs = 500;
static uint8_t phase = 0;
static uint32_t phaseEndsAtMs = 0;
static uint32_t buzzerOffAtMs = 0;

static void allOutputsOff() {
  for (uint8_t pin : kLedPins) digitalWrite(pin, RGB_OFF);
  digitalWrite(BUZZER, BUZZER_OFF);
}

static void enterPhase(uint8_t nextPhase) {
  allOutputsOff();
  phase = nextPhase;
  if (phase < 3) digitalWrite(kLedPins[phase], RGB_ON);
  if (phase == 0) {
    digitalWrite(BUZZER, BUZZER_ON);
    buzzerOffAtMs = millis() + kBuzzerPulseMs;
  } else {
    buzzerOffAtMs = 0;
  }
  phaseEndsAtMs = millis() + kPhaseMs[phase];
  Serial.printf("PHASE=%s GPIO=%d BUZZER=%s\n", kPhaseNames[phase],
                phase < 3 ? static_cast<int>(kLedPins[phase]) : -1,
                phase == 0 ? "ON" : "OFF");
}

void setup() {
  const uint8_t pins[] = {RGB_RED, RGB_GREEN, RGB_BLUE, BUZZER};
  for (uint8_t pin : pins) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
  Serial.begin(SERIAL_BAUD);
  Serial.println("Gym Spotter automatic RGB and buzzer power test");
  Serial.printf("RED=%u GREEN=%u BLUE=%u BUZZER=%u\n",
                RGB_RED, RGB_GREEN, RGB_BLUE, BUZZER);
  enterPhase(0);
}

void loop() {
  const uint32_t now = millis();
  if (buzzerOffAtMs != 0 && static_cast<int32_t>(now - buzzerOffAtMs) >= 0) {
    digitalWrite(BUZZER, BUZZER_OFF);
    buzzerOffAtMs = 0;
    Serial.println("BUZZER_OFF");
  }
  if (static_cast<int32_t>(now - phaseEndsAtMs) >= 0) {
    enterPhase(static_cast<uint8_t>((phase + 1) % 4));
  }
  delay(1);
}
