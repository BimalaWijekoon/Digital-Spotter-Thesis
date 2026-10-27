#pragma once
#include <Arduino.h>

// Actual assembled Gym Spotter ESP32-C3 PCB, verified 2026-10-17.
// GPIO numbers, NOT physical header positions.
namespace GymSpotterPins {
constexpr uint8_t IMU_SDA = 18;
constexpr uint8_t IMU_SCL = 19;
constexpr uint32_t I2C_HZ = 100000;
// Observed on the assembled PCB: GPIO0 lit green and GPIO1 lit red.
// GPIO3 is the handoff-reported blue channel; visible colour awaits observation.
constexpr uint8_t RGB_RED = 1;
constexpr uint8_t RGB_GREEN = 0;
constexpr uint8_t RGB_BLUE = 3;
constexpr uint8_t BUZZER = 10; // Drives R25 -> NPN base, not buzzer power.
constexpr uint8_t RGB_ON = HIGH;  // External common-ground RGB circuit.
constexpr uint8_t RGB_OFF = LOW;
constexpr uint8_t BUZZER_ON = HIGH;
constexpr uint8_t BUZZER_OFF = LOW;
constexpr uint32_t SERIAL_BAUD = 115200;
constexpr uint8_t IMU_EXPECTED_ADDRESS = 0x68; // AD0 physically grounded.
}
