#pragma once

#include <stdint.h>

// Assembled wearable PCB. GPIO numbers, not physical header positions.
// Red/green mapping and external-power buzzer were owner-observed 2026-10-17.
namespace WearablePcbPins {
constexpr uint8_t IMU_SDA = 18;
constexpr uint8_t IMU_SCL = 19;
constexpr uint8_t RGB_RED = 1;
constexpr uint8_t RGB_GREEN = 0;
constexpr uint8_t RGB_BLUE = 3;
constexpr uint8_t BUZZER = 10;  // R25 -> Q7 base; HIGH activates the buzzer.
}
