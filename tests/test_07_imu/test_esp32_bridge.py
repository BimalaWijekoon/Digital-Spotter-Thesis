"""
tests/test_07_imu/test_esp32_bridge.py
Purpose: Test ESP32Bridge mock mode.
Author: bimalawijekoon
Version: 1.0.0
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from imu.esp32_bridge import ESP32Bridge


class TestESP32Bridge:
    def test_bridge_initializes(self):
        bridge = ESP32Bridge()
        assert bridge.is_mock
        assert not bridge.is_connected()

    def test_mock_connect(self):
        bridge = ESP32Bridge()
        assert bridge.connect()
        assert bridge.is_connected()

    def test_mock_read_sample(self):
        bridge = ESP32Bridge()
        bridge.connect()
        sample = bridge.read_sample()
        assert "acc_x" in sample
        assert "acc_y" in sample
        assert "gyro_x" in sample
        assert "v_bar_velocity" in sample
        assert "timestamp_ms" in sample

    def test_mock_sample_plausible(self):
        bridge = ESP32Bridge()
        bridge.connect()
        sample = bridge.read_sample()
        assert -20 < sample["acc_y"] < 0  # gravity-like
        assert -50 < sample["gyro_x"] < 50

    def test_empty_sample_when_disconnected(self):
        bridge = ESP32Bridge()
        sample = bridge.read_sample()
        assert sample["acc_x"] == 0.0
        assert sample["acc_y"] == 0.0

    def test_disconnect(self):
        bridge = ESP32Bridge()
        bridge.connect()
        bridge.disconnect()
        assert not bridge.is_connected()
