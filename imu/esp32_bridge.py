"""
imu/esp32_bridge.py
Purpose: MQTT bridge to ESP32-C3 IMU sensor over HiveMQ Cloud.
         Implements the full 4-topic command/control protocol:
           PUB  digitalspotter/cmd    — Commands to ESP32 (start, stop, ping, identify)
           SUB  digitalspotter/status — Heartbeats + acks from ESP32
           SUB  digitalspotter/imu   — Sensor data stream (only when STREAMING)
           PUB  digitalspotter/result — Inference results (good/bad form feedback)
         Falls back to mock mode if MQTT is disabled or broker is unavailable.
Author: bimalawijekoon
Version: 3.0.0
Last Modified: 2026-07-03
"""

import json
import logging
import threading
import time
import math
import uuid
from pathlib import Path
from typing import Optional

import numpy as np

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.config import Config

logger = logging.getLogger(__name__)

# Attempt paho-mqtt import
try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    logger.warning("paho-mqtt not installed — run: pip install paho-mqtt")


class ESP32Bridge:
    """MQTT command/control bridge to ESP32-C3 over HiveMQ Cloud.

    Topics published BY THIS CLASS:
        digitalspotter/cmd    — Commands (start, stop, ping, identify)
        digitalspotter/result — Inference results (good/bad form)

    Topics subscribed BY THIS CLASS:
        digitalspotter/status — ESP32 heartbeats, acks, error reports
        digitalspotter/imu    — Live IMU sensor data

    Usage:
        bridge = ESP32Bridge()
        bridge.connect()
        bridge.start_session()          # tells ESP32 to stream
        sample = bridge.read_sample()   # get latest IMU dict
        bridge.publish_result(True, 0.9)# send bad-form result
        bridge.stop_session()           # tells ESP32 to stop
    """

    # Topics
    TOPIC_CMD    = "digitalspotter/cmd"    # Pi → ESP32
    TOPIC_RESULT = "digitalspotter/result" # Pi → ESP32
    TOPIC_STATUS = "digitalspotter/status" # ESP32 → Pi
    TOPIC_IMU    = "digitalspotter/imu"    # ESP32 → Pi

    # Timeouts
    ACK_TIMEOUT_S    = 8.0   # Max wait for start/stop ack from ESP32
    ONLINE_TIMEOUT_S = 12.0  # ESP32 considered offline if no heartbeat in 12s

    def __init__(self):
        self._connected     = False
        self._is_mock       = not MQTT_AVAILABLE or not Config.MQTT.ENABLED
        self._lock          = threading.Lock()
        self._client: Optional[mqtt.Client] = None

        # IMU data
        self._latest_sample   = None
        self._last_data_time  = 0.0

        # ESP32 state tracking (from heartbeats)
        self._esp32_state     = "offline"  # idle / streaming / error / offline
        self._esp32_last_hb   = 0.0        # last heartbeat timestamp
        self._esp32_rssi      = None        # int dBm
        self._esp32_uptime_ms = 0           # ESP32 uptime_ms from last heartbeat
        self._esp32_free_heap = 0
        self._esp32_session   = None        # session_id currently on ESP32

        # Ack synchronisation — used by start_session / stop_session
        self._ack_event:  dict[str, threading.Event] = {}

        if self._is_mock:
            logger.info("ESP32Bridge: MOCK mode (MQTT disabled or paho not installed)")

    # ─── Connection ──────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to HiveMQ Cloud. Returns True on success (or mock mode)."""
        if self._is_mock:
            self._connected    = True
            self._esp32_state  = "idle"    # Mock pretends ESP32 is idle
            self._esp32_last_hb = time.time()
            logger.info("ESP32Bridge: MOCK connected")
            return True

        try:
            self._client = mqtt.Client(
                client_id=f"digital-spotter-pi-{uuid.uuid4().hex[:6]}",
                protocol=mqtt.MQTTv311,
            )
            self._client.username_pw_set(Config.MQTT.USERNAME, Config.MQTT.PASSWORD)
            self._client.tls_set()  # System CA certs — works with HiveMQ Cloud

            self._client.on_connect    = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message    = self._on_message

            self._client.connect(Config.MQTT.BROKER, Config.MQTT.PORT, keepalive=30)
            self._client.loop_start()  # Background network thread

            # Wait up to 8 s for CONNACK
            deadline = time.time() + 8.0
            while not self._connected and time.time() < deadline:
                time.sleep(0.1)

            if self._connected:
                logger.info("ESP32Bridge: Connected to %s:%d",
                            Config.MQTT.BROKER, Config.MQTT.PORT)
                return True
            else:
                logger.error("ESP32Bridge: MQTT connection timed out — using mock")
                self._is_mock  = True
                self._connected = True
                return False

        except Exception as e:
            logger.error("ESP32Bridge: connect error: %s — using mock", e)
            self._is_mock  = True
            self._connected = True
            return False

    def disconnect(self):
        """Disconnect from HiveMQ Cloud."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
        self._connected    = False
        self._esp32_state  = "offline"
        logger.info("ESP32Bridge: Disconnected")

    # ─── Session control ─────────────────────────────────────────────────────

    def start_session(self, session_id: str = None) -> bool:
        """Send 'start' command to ESP32 and wait for ack_start.

        Args:
            session_id: Optional session label. Auto-generated if not provided.

        Returns:
            True if ESP32 acknowledged within ACK_TIMEOUT_S seconds.
        """
        if session_id is None:
            session_id = f"s-{uuid.uuid4().hex[:8]}"

        if self._is_mock:
            self._esp32_state  = "streaming"
            self._esp32_session = session_id
            logger.info("ESP32Bridge MOCK: session started (%s)", session_id)
            return True

        evt = threading.Event()
        self._ack_event["ack_start"] = evt

        payload = json.dumps({"cmd": "start", "session_id": session_id})
        self._publish(self.TOPIC_CMD, payload, qos=1)
        logger.info("[CMD] start → session_id=%s", session_id)

        ok = evt.wait(timeout=self.ACK_TIMEOUT_S)
        self._ack_event.pop("ack_start", None)

        if ok:
            self._esp32_session = session_id
            logger.info("[CMD] start ack received — ESP32 streaming")
        else:
            logger.warning("[CMD] start ack TIMEOUT after %.0fs", self.ACK_TIMEOUT_S)

        return ok

    def stop_session(self) -> bool:
        """Send 'stop' command to ESP32 and wait for ack_stop.

        Returns:
            True if ESP32 acknowledged within ACK_TIMEOUT_S seconds.
        """
        if self._is_mock:
            self._esp32_state  = "idle"
            self._esp32_session = None
            logger.info("ESP32Bridge MOCK: session stopped")
            return True

        evt = threading.Event()
        self._ack_event["ack_stop"] = evt

        self._publish(self.TOPIC_CMD, json.dumps({"cmd": "stop"}), qos=1)
        logger.info("[CMD] stop sent")

        ok = evt.wait(timeout=self.ACK_TIMEOUT_S)
        self._ack_event.pop("ack_stop", None)

        if ok:
            self._esp32_session = None
            logger.info("[CMD] stop ack received — ESP32 idle")
        else:
            logger.warning("[CMD] stop ack TIMEOUT — forcing state to idle")
            with self._lock:
                self._esp32_state = "idle"

        return ok

    def ping(self) -> bool:
        """Send ping command. Returns True if a heartbeat arrives within 3 s."""
        if self._is_mock:
            return True

        evt = threading.Event()
        self._ack_event["heartbeat"] = evt
        self._publish(self.TOPIC_CMD, json.dumps({"cmd": "ping"}), qos=0)
        ok = evt.wait(timeout=3.0)
        self._ack_event.pop("heartbeat", None)
        return ok

    def identify(self):
        """Send identify command — ESP32 flashes rainbow LED for 3 s."""
        self._publish(self.TOPIC_CMD, json.dumps({"cmd": "identify"}), qos=0)
        logger.info("[CMD] identify sent")

    def set_imu_streaming(self, enabled: bool) -> bool:
        """Toggle IMU publishing on the ESP32 without ending the session.

        Sends 'imu_on' / 'imu_off' to the ESP32. Used by the dashboard sensor
        toggle to throttle MQTT traffic on demand. Default (device boot) is ON.

        Args:
            enabled: True = resume publishing, False = pause publishing.

        Returns:
            True (command dispatched; mock mode just tracks the flag).
        """
        cmd = "imu_on" if enabled else "imu_off"
        if self._is_mock:
            logger.info("ESP32Bridge MOCK: IMU streaming %s", "ON" if enabled else "OFF")
            return True
        self._publish(self.TOPIC_CMD, json.dumps({"cmd": cmd}), qos=1)
        logger.info("[CMD] %s sent", cmd)
        return True

    # ─── Data access ─────────────────────────────────────────────────────────

    def read_sample(self) -> dict:
        """Return the latest IMU sample dict."""
        if not self._connected:
            return self._empty_sample()

        if self._is_mock:
            return self._mock_sample()

        with self._lock:
            if self._latest_sample is not None:
                return self._latest_sample.copy()

        return self._empty_sample()

    def publish_result(self, is_bad_form: bool, confidence: float):
        """Publish inference result to ESP32 for simultaneous buzzer feedback.

        Both good AND bad form results are sent — ESP32 buzzer fires for both.
        """
        payload = json.dumps({
            "bad_form":   is_bad_form,
            "confidence": round(float(confidence), 4),
            "ts":         int(time.time() * 1000),
        })
        self._publish(self.TOPIC_RESULT, payload, qos=0)
        logger.debug("[RESULT] bad_form=%s conf=%.3f", is_bad_form, confidence)

    # ─── Status properties ────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        return self._connected

    @property
    def esp32_state(self) -> str:
        """ESP32 state string: idle / streaming / error / offline"""
        if self._is_mock:
            return self._esp32_state
        if time.time() - self._esp32_last_hb > self.ONLINE_TIMEOUT_S:
            return "offline"
        return self._esp32_state

    @property
    def esp32_online(self) -> bool:
        """True if ESP32 heartbeat received within ONLINE_TIMEOUT_S."""
        if self._is_mock:
            return self._connected
        return time.time() - self._esp32_last_hb < self.ONLINE_TIMEOUT_S

    @property
    def esp32_rssi(self) -> Optional[int]:
        return self._esp32_rssi

    @property
    def esp32_uptime_ms(self) -> int:
        return self._esp32_uptime_ms

    @property
    def esp32_free_heap(self) -> int:
        return self._esp32_free_heap

    @property
    def esp32_session_id(self) -> Optional[str]:
        return self._esp32_session

    @property
    def data_is_flowing(self) -> bool:
        """True if ESP32 is in streaming state AND recently sent IMU data."""
        if self._is_mock:
            return self._connected and self._esp32_state == "streaming"
        return (self.esp32_state == "streaming" and
                self._connected and
                (time.time() - self._last_data_time) < 3.0)

    @property
    def is_mock(self) -> bool:
        return self._is_mock

    # ─── MQTT callbacks ───────────────────────────────────────────────────────

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            client.subscribe(self.TOPIC_STATUS, qos=0)
            client.subscribe(self.TOPIC_IMU,    qos=0)
            logger.info("[MQTT] Connected — subscribed status + imu")
        else:
            logger.error("[MQTT] Connection refused rc=%d", rc)

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if rc != 0:
            logger.warning("[MQTT] Unexpected disconnect rc=%d — auto-reconnecting", rc)

    def _on_message(self, client, userdata, msg):
        try:
            if msg.topic == self.TOPIC_STATUS:
                self._handle_status(msg.payload.decode("utf-8"))
            elif msg.topic == self.TOPIC_IMU:
                self._handle_imu(msg.payload.decode("utf-8"))
        except Exception as e:
            logger.warning("[MQTT] Message error on %s: %s", msg.topic, e)

    def _handle_status(self, raw: str):
        """Parse ESP32 status message (heartbeats, acks, errors)."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[STATUS] Bad JSON: %s", raw)
            return

        event = data.get("event", "")
        state = data.get("state", self._esp32_state)

        with self._lock:
            self._esp32_state     = state
            self._esp32_last_hb   = time.time()
            if "wifi_rssi"   in data: self._esp32_rssi      = data["wifi_rssi"]
            if "uptime_ms"   in data: self._esp32_uptime_ms  = data["uptime_ms"]
            if "free_heap"   in data: self._esp32_free_heap  = data["free_heap"]
            if "session_id"  in data: self._esp32_session    = data["session_id"] or None

        logger.debug("[STATUS] event=%s state=%s rssi=%s", event, state, self._esp32_rssi)

        # Signal ack waiters
        if event in self._ack_event:
            self._ack_event[event].set()
        # Heartbeat ping ack
        if event == "heartbeat" and "heartbeat" in self._ack_event:
            self._ack_event["heartbeat"].set()

    def _handle_imu(self, raw: str):
        """Parse incoming IMU data packet from ESP32."""
        try:
            data = json.loads(raw)
            sample = {
                "acc_x":           float(data.get("ax", 0.0)),
                "acc_y":           float(data.get("ay", 0.0)),
                "acc_z":           float(data.get("az", 0.0)),
                "gyro_x":          float(data.get("gx", 0.0)),
                "gyro_y":          float(data.get("gy", 0.0)),
                "gyro_z":          float(data.get("gz", 0.0)),
                "v_bar_velocity":  0.0,
                "p_bar_power":     0.0,
                "smoothness_jerk": 0.0,
                "timestamp_ms":    int(data.get("ts", time.time() * 1000)),
            }
            with self._lock:
                self._latest_sample  = sample
                self._last_data_time = time.time()
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("[IMU] Malformed packet: %s", e)

    # ─── Internal helpers ─────────────────────────────────────────────────────

    def _publish(self, topic: str, payload: str, qos: int = 0):
        if self._is_mock:
            return
        if self._client and self._connected:
            self._client.publish(topic, payload, qos=qos)

    def _mock_sample(self) -> dict:
        """Synthetic IMU data simulating a barbell deadlift."""
        t     = time.time()
        phase = math.sin(2 * math.pi * 0.33 * t)
        acc_x   = float(np.random.normal(0,    0.1))
        acc_y   = float(-9.81 + phase * 2.0 + np.random.normal(0, 0.2))
        acc_z   = float(np.random.normal(0,    0.1))
        gyro_x  = float(np.random.normal(0,    5.0))
        gyro_y  = float(np.random.normal(0,    5.0))
        gyro_z  = float(np.random.normal(0,    2.0))
        velocity = abs(phase) * 0.6 + float(np.random.normal(0, 0.02))
        return {
            "acc_x": acc_x, "acc_y": acc_y, "acc_z": acc_z,
            "gyro_x": gyro_x, "gyro_y": gyro_y, "gyro_z": gyro_z,
            "v_bar_velocity":  velocity,
            "p_bar_power":     velocity * 80.0 * 9.81,
            "smoothness_jerk": float(np.random.normal(0, 0.5)),
            "timestamp_ms":    int(time.time() * 1000),
        }

    def _empty_sample(self) -> dict:
        return {
            "acc_x": 0.0, "acc_y": 0.0, "acc_z": 0.0,
            "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0,
            "v_bar_velocity": 0.0, "p_bar_power": 0.0,
            "smoothness_jerk": 0.0,
            "timestamp_ms": int(time.time() * 1000),
        }
