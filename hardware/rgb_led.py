"""
hardware/rgb_led.py
Purpose: RGB 5050 SMD LED control via GPIO PWM — visual form feedback.
         Synchronized with ESP32-C3 LED animations using a background thread.
         Falls back to mock (no-op) mode on non-Pi platforms.
Author: bimalawijekoon
Version: 2.0.0
Last Modified: 2026-07-03
"""

import logging
import threading
import time
import math
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logger.info("RPi.GPIO not available — RGB LED in mock mode")


class RgbLed:
    """RGB 5050 SMD LED controller using GPIO PWM.

    Drives a common-cathode or common-anode RGB LED module via
    3 PWM-capable GPIO pins. Uses a background thread to render smooth
    pulsing/breathing animations to exactly match the ESP32 firmware.
    """

    # Predefined colors
    OFF     = (0, 0, 0)
    RED     = (255, 0, 0)
    GREEN   = (0, 255, 0)
    BLUE    = (0, 0, 255)
    AMBER   = (255, 100, 0)
    CYAN    = (0, 255, 255)
    WHITE   = (255, 255, 255)
    PURPLE  = (180, 0, 255)

    def __init__(self, pin_r=None, pin_g=None, pin_b=None,
                 common_anode=False, enabled=None):
        self._pin_r = pin_r if pin_r is not None else Config.RGB_LED.PIN_R
        self._pin_g = pin_g if pin_g is not None else Config.RGB_LED.PIN_G
        self._pin_b = pin_b if pin_b is not None else Config.RGB_LED.PIN_B
        self._common_anode = common_anode
        self._enabled = enabled if enabled is not None else Config.RGB_LED.ENABLED
        self._is_mock = not GPIO_AVAILABLE
        self._is_setup = False
        
        self._pwm_r = None
        self._pwm_g = None
        self._pwm_b = None

        # Animation State Machine
        self._lock = threading.Lock()
        
        # Base state (persists)
        self._base_mode   = "solid"
        self._base_color  = self.OFF
        self._base_period = 1000
        
        # Current active state (can be a temporary override)
        self._mode        = "solid"
        self._color       = self.OFF
        self._period_ms   = 1000
        
        self._temp_end_time = 0.0
        self._flash_on      = False
        self._last_toggle   = 0.0
        self._last_mock_log = None

        self._running = True

        if not self._is_mock and self._enabled:
            self._setup_gpio()

        if self._enabled:
            self._thread = threading.Thread(target=self._anim_loop, daemon=True)
            self._thread.start()

    def _setup_gpio(self):
        """Configure GPIO pins with PWM at 1kHz."""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._pin_r, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self._pin_g, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self._pin_b, GPIO.OUT, initial=GPIO.LOW)

            # 100Hz is much more stable for RPi.GPIO software PWM under heavy CPU load
            # than 1000Hz, which causes microsecond jitter and flashing at low duty cycles.
            self._pwm_r = GPIO.PWM(self._pin_r, 100)
            self._pwm_g = GPIO.PWM(self._pin_g, 100)
            self._pwm_b = GPIO.PWM(self._pin_b, 100)

            self._pwm_r.start(0)
            self._pwm_g.start(0)
            self._pwm_b.start(0)

            self._is_setup = True
            logger.info("RGB LED initialized on GPIO R=%d G=%d B=%d",
                        self._pin_r, self._pin_g, self._pin_b)
        except Exception as e:
            logger.error("Failed to setup RGB LED: %s", e)
            self._is_mock = True

    # ─── Animation Loop ───────────────────────────────────────────────────────

    def _anim_loop(self):
        """Background thread rendering animations at ~50Hz."""
        while self._running:
            now = time.time()
            
            with self._lock:
                # Revert temp state if expired
                if self._temp_end_time > 0 and now > self._temp_end_time:
                    self._temp_end_time = 0.0
                    self._mode = self._base_mode
                    self._color = self._base_color
                    self._period_ms = self._base_period
                
                mode = self._mode
                color = self._color
                period = self._period_ms
            
            if mode == "solid":
                self._apply_color(color)
                time.sleep(0.05)
                
            elif mode == "pulse":
                # Match ESP32 sinewave breathing
                now_ms = int(now * 1000)
                ph = (now_ms % period) / float(period)
                br = 0.5 * (1.0 + math.sin(2.0 * math.pi * ph - math.pi / 2.0))
                r = int(color[0] * br)
                g = int(color[1] * br)
                b = int(color[2] * br)
                self._apply_color((r, g, b))
                time.sleep(0.02) # 50Hz update
                
            elif mode == "flash":
                if now - self._last_toggle > (period / 1000.0):
                    self._flash_on = not self._flash_on
                    self._last_toggle = now
                
                if self._flash_on:
                    self._apply_color(color)
                else:
                    self._apply_color(self.OFF)
                time.sleep(0.02)
            else:
                self._apply_color(self.OFF)
                time.sleep(0.1)

    def _apply_color(self, rgb):
        """Low-level PWM color application."""
        r, g, b = rgb
        
        if self._is_mock:
            if rgb != self._last_mock_log:
                logger.debug("RGB MOCK: (%d, %d, %d)", r, g, b)
                self._last_mock_log = rgb
            return

        dr = (r / 255.0) * 100.0
        dg = (g / 255.0) * 100.0
        db = (b / 255.0) * 100.0

        if self._common_anode:
            dr = 100.0 - dr
            dg = 100.0 - dg
            db = 100.0 - db

        if self._is_setup:
            try:
                self._pwm_r.ChangeDutyCycle(dr)
                self._pwm_g.ChangeDutyCycle(dg)
                self._pwm_b.ChangeDutyCycle(db)
            except Exception:
                pass

    # ─── State Controllers ────────────────────────────────────────────────────

    def _set_base(self, mode, color, period=1000):
        if not self._enabled: return
        with self._lock:
            self._base_mode = mode
            self._base_color = color
            self._base_period = period
            if self._temp_end_time == 0:
                self._mode = mode
                self._color = color
                self._period_ms = period

    def _set_temp(self, mode, color, period=1000, duration_sec=2.0):
        if not self._enabled: return
        with self._lock:
            self._mode = mode
            self._color = color
            self._period_ms = period
            self._temp_end_time = time.time() + duration_sec
            self._flash_on = True
            self._last_toggle = time.time()

    def idle(self):
        """Set LED to slow green breathe — system idle/standby."""
        self._set_base("pulse", self.GREEN, 1200)

    def processing(self):
        """Set LED to fast cyan breathe — inference session active."""
        self._set_base("pulse", self.CYAN, 400)

    def good_form(self):
        """Solid green for 2 seconds, then revert to processing state."""
        self._set_temp("solid", self.GREEN, duration_sec=2.0)

    def bad_form(self):
        """Flash red for 2 seconds, then revert to processing state."""
        self._set_temp("flash", self.RED, period=150, duration_sec=2.0)

    def off(self):
        """Turn LED completely off."""
        self._set_base("solid", self.OFF)

    def set_color(self, rgb):
        """Manually force a solid color (used by test endpoints)."""
        self._set_base("solid", rgb)

    # ─── Properties & Cleanup ─────────────────────────────────────────────────

    @property
    def is_mock(self):
        return self._is_mock

    @property
    def is_enabled(self):
        return self._enabled

    def cleanup(self):
        self._running = False
        if self._enabled and hasattr(self, '_thread'):
            self._thread.join(timeout=1.0)
            
        if not self._is_mock and self._is_setup:
            try:
                self._pwm_r.stop()
                self._pwm_g.stop()
                self._pwm_b.stop()
                GPIO.cleanup([self._pin_r, self._pin_g, self._pin_b])
                logger.info("RGB LED GPIO cleaned up")
            except Exception as e:
                logger.error("RGB cleanup error: %s", e)

    def __del__(self):
        self.cleanup()
