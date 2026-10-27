"""
scripts/dashboard/main.py
Purpose: Pi-targeted production dashboard backend — FastAPI server for 
         inference testing, live MJPEG streaming, and IMU data logging.
Author: bimalawijekoon
Version: 2.1.0
Last Modified: 2026-06-30
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import asyncio
import numpy as np
import logging
import time
import os
from pathlib import Path
from typing import List, Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.config import Config
from config.constants import FEATURE_ORDER, TOTAL_FEATURES, SEQUENCE_LENGTH_MODEL
from inference.lstm_runner import LSTMRunner
from inference.preprocessor import Preprocessor
from hardware.buzzer import Buzzer
from hardware.rgb_led import RgbLed
from imu.esp32_bridge import ESP32Bridge
from integration.session_manager import SessionManager
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
import cv2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def get_cpu_temp() -> float:
    """Read the internal CPU temperature of the Raspberry Pi."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return round(float(f.read().strip()) / 1000.0, 1)
    except Exception:
        return 0.0


def _build_camera_placeholder() -> bytes:
    """Render a static 'Camera Off' frame (JPEG bytes) for /video_feed.

    Shown whenever the camera is disabled so the dashboard has something to
    display while running on pre-loaded data.
    """
    import numpy as _np
    img = _np.zeros((360, 640, 3), dtype=_np.uint8)
    img[:] = (18, 18, 22)  # dark card background (BGR)
    cv2.putText(img, "CAMERA OFF", (150, 170),
                cv2.FONT_HERSHEY_SIMPLEX, 1.4, (90, 90, 110), 3, cv2.LINE_AA)
    cv2.putText(img, "Running on pre-loaded data", (150, 215),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (70, 70, 90), 1, cv2.LINE_AA)
    ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes() if ok else b""


# ─────────────────────────────────────────────────────────────────
# Pydantic request models — matches v4 40-feature contract
# ─────────────────────────────────────────────────────────────────

class SubjectInfo(BaseModel):
    height_cm: float = Field(175.0, description="Subject height in cm")
    weight_kg: float = Field(75.0, description="Subject weight in kg")
    femur_tibia_ratio: float = Field(1.20, description="Femur-to-tibia ratio")


class SessionInfo(BaseModel):
    exercise_id: int = Field(0, description="0=Squat, 1=Deadlift")
    load_kg: float = Field(60.0, description="Barbell load in kg")


class PhaseData(BaseModel):
    """One phase of sensor data — 32 raw features (context + vision + angles
    + IMU + bar performance). The remaining 8 engineered features are
    computed server-side from these inputs."""
    rep_phase: int = Field(..., ge=1, le=3)

    # Vision joints (16)
    vis_l_shoulder_x: float = 0.0
    vis_l_shoulder_y: float = 0.0
    vis_r_shoulder_x: float = 0.0
    vis_r_shoulder_y: float = 0.0
    vis_l_hip_x: float = 0.0
    vis_l_hip_y: float = 0.0
    vis_r_hip_x: float = 0.0
    vis_r_hip_y: float = 0.0
    vis_l_knee_x: float = 0.0
    vis_l_knee_y: float = 0.0
    vis_r_knee_x: float = 0.0
    vis_r_knee_y: float = 0.0
    vis_l_ankle_x: float = 0.0
    vis_l_ankle_y: float = 0.0
    vis_r_ankle_x: float = 0.0
    vis_r_ankle_y: float = 0.0

    # Trunk angle (1)
    angle_trunk_inclination: float = 0.0

    # IMU (6)
    imu_acc_x: float = 0.0
    imu_acc_y: float = 0.0
    imu_acc_z: float = 0.0
    imu_gyro_x: float = 0.0
    imu_gyro_y: float = 0.0
    imu_gyro_z: float = 0.0

    # Bar performance (3)
    v_bar_velocity_vertical: float = 0.0
    p_bar_power_watts: float = 0.0
    smoothness_jerk: float = 0.0

    # Angle asymmetries (3)
    hip_flexion_asymmetry: float = 0.0
    knee_flexion_asymmetry: float = 0.0
    ankle_dorsiflexion_asymmetry: float = 0.0

    # Engineered features (4) — can be overridden, otherwise computed
    imu_acc_magnitude: Optional[float] = None
    knee_hip_coupling_l: Optional[float] = None
    knee_hip_coupling_r: Optional[float] = None
    velocity_decel_ratio: Optional[float] = None


class PredictionRequest(BaseModel):
    subject: SubjectInfo
    session: SessionInfo
    phases: List[PhaseData] = Field(..., min_length=3, max_length=3)


# ─────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Digital Spotter — Production Dashboard API",
    description="Pi-targeted full system dashboard with live camera and sensor fusion",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
_session_manager: SessionManager = None
_buzzer: Buzzer = None
_rgb: RgbLed = None
_session_active: bool = False
_auto_predict: bool = False
_active_websockets: List[WebSocket] = []
_background_tasks: List[asyncio.Task] = []

# Demo toggles (controllable from the dashboard):
#   _sensor_on — whether the ESP32 IMU is publishing over MQTT. Default ON.
#   _camera_on — whether the live camera pipeline is running. Default OFF so the
#                demo can run on pre-loaded data without depending on the camera.
_sensor_on: bool = True
_camera_on: bool = False
_camera_placeholder_jpeg: bytes = b""

def _on_rep_complete(rep_data: dict):
    """Callback when a rep phase is completed."""
    pass # Can broadcast via websocket if needed

def _on_inference_complete(result_data: dict):
    """Callback when inference completes via the automated pipeline."""
    if not _auto_predict:
        # Just broadcast the result so dashboard can display it, but no feedback loop
        for ws in _active_websockets:
            asyncio.create_task(ws.send_json({"type": "inference_result", "data": result_data}))
        return

    _bridge = _session_manager._imu_bridge if _session_manager else None

    # Automated buzzer/rgb feedback
    if result_data.get("is_bad_form"):
        if _buzzer and _buzzer.is_enabled:
            _buzzer.beep_bad_form()
        if _rgb and _rgb.is_enabled:
            _rgb.bad_form()
        if _bridge:
            _bridge.publish_result(True, result_data.get("confidence", 0.0))
    else:
        if _rgb and _rgb.is_enabled:
            _rgb.good_form()
        if _buzzer and _buzzer.is_enabled:
            _buzzer.beep_good_form()
        if _bridge:
            _bridge.publish_result(False, result_data.get("confidence", 0.0))

    # Broadcast to all connected websockets
    for ws in _active_websockets:
        asyncio.create_task(ws.send_json({"type": "inference_result", "data": result_data}))


@app.on_event("startup")
async def startup():
    """Load model, preprocessor, and initialize hardware at startup."""
    global _session_manager, _buzzer, _rgb, _background_tasks

    logger.info("Initializing full production system pipeline...")

    _buzzer = Buzzer()
    logger.info("✓ Buzzer initialized (mock=%s, pin=%d)", _buzzer.is_mock, Config.BUZZER.GPIO_PIN)

    _rgb = RgbLed()
    _rgb.idle()
    logger.info("✓ RGB LED initialized (mock=%s, pins=%d,%d,%d)", 
                _rgb.is_mock, Config.RGB_LED.PIN_R, Config.RGB_LED.PIN_G, Config.RGB_LED.PIN_B)

    # Initialize session manager which loads models, bridge, and frame processor
    _session_manager = SessionManager(
        on_rep_complete=_on_rep_complete,
        on_inference=_on_inference_complete
    )
    # The ESP32Bridge connects during SessionManager init
    logger.info("✓ SessionManager initialized")

    # Build the "Camera Off" placeholder frame shown by /video_feed when the
    # camera is disabled (demo default).
    global _camera_placeholder_jpeg
    _camera_placeholder_jpeg = _build_camera_placeholder()

    # Camera is OFF by default (demo runs on pre-loaded data). The frame
    # processing loop is started on demand via /toggle-camera.
    logger.info("Camera default: OFF (toggle via /toggle-camera)")

    # Keep ownership of long-running tasks so shutdown can cancel and await them.
    _background_tasks = [
        asyncio.create_task(
            _monitor_connection(), name="digital-spotter-connection-monitor"
        ),
        asyncio.create_task(
            _broadcast_live_data(), name="digital-spotter-telemetry-broadcast"
        ),
    ]

    logger.info("Production Dashboard ready — v4 model, %d features, threshold=%.3f",
                TOTAL_FEATURES, Config.INFERENCE.DECISION_THRESHOLD)


@app.on_event("shutdown")
async def shutdown():
    """Clean up GPIO and MQTT on shutdown."""
    for task in _background_tasks:
        task.cancel()
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
        _background_tasks.clear()

    if _session_manager:
        _session_manager._frame_processor.stop()
        _session_manager._imu_bridge.disconnect()
    if _buzzer:
        _buzzer.cleanup()
    if _rgb:
        _rgb.cleanup()


# ─────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────

@app.get("/")
async def serve_dashboard():
    """Serve the dashboard HTML."""
    index_path = Path(__file__).parent / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return {"error": "index.html not found", "expected": str(index_path)}


@app.get("/cam_test")
async def serve_cam_test():
    """Serve the simple standalone camera test HTML."""
    index_path = Path(__file__).parent / "cam_test.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return {"error": "cam_test.html not found", "expected": str(index_path)}



@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ready" if _session_manager else "degraded",
        "model_loaded": _session_manager._lstm_runner.is_loaded() if _session_manager else False,
        "model_mock": _session_manager._lstm_runner.is_mock if _session_manager else True,
        "preprocessor_mock": _session_manager._lstm_runner._preprocessor.is_mock if _session_manager else True,
        "buzzer_enabled": _buzzer.is_enabled if _buzzer else False,
        "buzzer_mock": _buzzer.is_mock if _buzzer else True,
        "buzzer_pin": Config.BUZZER.GPIO_PIN,
        "rgb_enabled": _rgb.is_enabled if _rgb else False,
        "rgb_mock": _rgb.is_mock if _rgb else True,
        "imu_connected": _session_manager._imu_bridge.is_connected() if _session_manager else False,
        "imu_mock": _session_manager._imu_bridge.is_mock if _session_manager else True,
        "threshold": Config.INFERENCE.DECISION_THRESHOLD,
        "features": TOTAL_FEATURES,
        "sequence_length": SEQUENCE_LENGTH_MODEL,
        "sensor_on": _sensor_on,
        "camera_on": _camera_on,
    }


async def _monitor_connection():
    """Background task: detect a genuine ESP32 disconnect during an active session.

    Important: pausing the IMU (sensor toggle → 'imu_off') stops IMU packets but
    the ESP32 keeps sending heartbeats, so it stays *online*. We therefore base
    "disconnected" on the heartbeat (esp32_online), NOT on IMU data flow — and we
    do NOT force-stop the session. The dashboard just shows an "IMU disconnected"
    notice; the session stays alive.
    """
    was_online = True
    while True:
        await asyncio.sleep(1.5)
        _bridge = _session_manager._imu_bridge if _session_manager else None
        if not (_session_active and _bridge):
            was_online = True
            continue
        online = _bridge.esp32_online
        # Edge-trigger the alert only on the online→offline transition.
        if was_online and not online:
            logger.warning("[MONITOR] ESP32 heartbeat lost during active session "
                           "(session kept alive; dashboard notified).")
            if _buzzer:
                _buzzer.beep_warning()          # Two slow beeps = component issue
            if _rgb and _rgb.is_enabled:
                _rgb.bad_form()                  # Red flash
        was_online = online


@app.post("/toggle-auto-predict")
async def toggle_auto_predict():
    """Toggle the automated inference feedback loop."""
    global _auto_predict
    _auto_predict = not _auto_predict
    return {"status": "ok", "auto_predict": _auto_predict}


@app.post("/toggle-sensor")
async def toggle_sensor():
    """Toggle ESP32 IMU publishing (throttle MQTT). Default ON.

    Sends 'imu_on'/'imu_off' to the ESP32. The device stays in the session
    either way — this only gates whether it publishes IMU samples.
    """
    global _sensor_on
    _sensor_on = not _sensor_on
    _bridge = _session_manager._imu_bridge if _session_manager else None
    if _bridge:
        _bridge.set_imu_streaming(_sensor_on)
    logger.info("Sensor streaming toggled → %s", "ON" if _sensor_on else "OFF")
    return {"status": "ok", "sensor_on": _sensor_on}


@app.post("/toggle-camera")
async def toggle_camera():
    """Toggle the live camera pipeline. Default OFF (demo uses pre-loaded data).

    Turning ON starts the frame processor (connects to the mediamtx RTSP
    stream); turning OFF stops it and /video_feed shows the placeholder.
    """
    global _camera_on
    _camera_on = not _camera_on
    fp = _session_manager._frame_processor if _session_manager else None
    if fp:
        try:
            if _camera_on:
                fp.start()
            else:
                fp.stop()
        except Exception as e:
            logger.warning("Camera toggle error: %s", e)
    logger.info("Camera toggled → %s", "ON" if _camera_on else "OFF")
    return {"status": "ok", "camera_on": _camera_on}

@app.get("/status")
async def system_status():
    """Detailed system readiness status for the init screen."""
    _runner = _session_manager._lstm_runner if _session_manager else None
    _preprocessor = _runner._preprocessor if _runner else None
    _bridge = _session_manager._imu_bridge if _session_manager else None

    model_ok   = bool(_runner and _runner.is_loaded())
    pre_ok     = bool(_preprocessor and _preprocessor.is_loaded())
    buzzer_ok  = _buzzer is not None
    rgb_ok     = _rgb is not None
    mqtt_ok    = bool(_bridge and _bridge.is_connected())
    data_ok    = bool(_bridge and _bridge.data_is_flowing)

    # Explain WHY each component is in mock mode (helps UI diagnostics)
    mock_reasons = {}
    if _runner and _runner.is_mock:
        mock_reasons["model"] = "TFLite model file not found — using random predictor"
    if _preprocessor and _preprocessor.is_mock:
        mock_reasons["preprocessor"] = "scaler.save / winsor_bounds.save not found"
    if _bridge and _bridge.is_mock:
        import paho.mqtt.client as _paho_check
        mqtt_available = True
    else:
        try:
            import paho.mqtt.client
            mqtt_available = True
        except ImportError:
            mqtt_available = False

    if _bridge and _bridge.is_mock:
        if not mqtt_available:
            mock_reasons["imu"] = "paho-mqtt not installed — run: pip install paho-mqtt"
        elif not Config.MQTT.ENABLED:
            mock_reasons["imu"] = "DS_MQTT_ENABLED=false in environment — check your .env file"
        elif not Config.MQTT.BROKER or Config.MQTT.BROKER == "localhost":
            mock_reasons["imu"] = "DS_MQTT_BROKER not set in .env"
        else:
            mock_reasons["imu"] = "MQTT connection failed — check broker/credentials"

    return {
        "model_ready":        model_ok,
        "model_mock":         _runner.is_mock if _runner else True,
        "preprocessor_ready": pre_ok,
        "preprocessor_mock":  _preprocessor.is_mock if _preprocessor else True,
        "buzzer_ready":       buzzer_ok,
        "buzzer_mock":        _buzzer.is_mock if _buzzer else True,
        "buzzer_pin":         Config.BUZZER.GPIO_PIN,
        "rgb_ready":          rgb_ok,
        "rgb_mock":           _rgb.is_mock if _rgb else True,
        "mqtt_connected":     mqtt_ok,
        "imu_mock":           _bridge.is_mock if _bridge else True,
        # Heartbeat-based ESP32 state (replaces simple data_is_flowing check)
        "esp32_online":       bool(_bridge and _bridge.esp32_online),
        "esp32_state":        _bridge.esp32_state if _bridge else "offline",
        "esp32_rssi":         _bridge.esp32_rssi if _bridge else None,
        "esp32_uptime_ms":    _bridge.esp32_uptime_ms if _bridge else 0,
        "esp32_free_heap":    _bridge.esp32_free_heap if _bridge else 0,
        "esp32_session_id":   _bridge.esp32_session_id if _bridge else None,
        "session_active":     _session_active,
        # all_ready: ESP32 must be online (heartbeat-based) — not just data flowing
        "all_ready":          all([model_ok, pre_ok, buzzer_ok, rgb_ok, mqtt_ok,
                                   bool(_bridge and _bridge.esp32_online)]),
        "threshold":          Config.INFERENCE.DECISION_THRESHOLD,
        "mock_reasons":       mock_reasons,
        "cpu_temp":           get_cpu_temp(),
        "sensor_on":          _sensor_on,
        "camera_on":          _camera_on,
        "env": {
            "mqtt_enabled":  Config.MQTT.ENABLED,
            "mqtt_broker":   Config.MQTT.BROKER,
            "mqtt_username": Config.MQTT.USERNAME or "(not set)",
        },
    }


@app.post("/session/start")
async def session_start(req: SessionInfo = None):
    """Start a session: send 'start' command to ESP32 and wait for ack.

    The ESP32 transitions IDLE → STREAMING and begins publishing IMU data.
    Pi LED and buzzer fire simultaneously with ESP32 on ack receipt.
    """
    global _session_active
    _bridge = _session_manager._imu_bridge if _session_manager else None

    if not (_bridge and _bridge.esp32_online):
        raise HTTPException(status_code=503,
                            detail="ESP32 not online — no heartbeat received")
    if _bridge.esp32_state == "streaming":
        raise HTTPException(status_code=409,
                            detail="ESP32 already streaming")

    # Start automated session via SessionManager
    if req:
        _session_manager.start_session(
            height_cm=175.0,
            weight_kg=75.0,
            ftr=1.20,
            exercise_id=req.exercise_id,
            load_kg=req.load_kg
        )
    else:
        _session_manager.start_session(
            height_cm=175.0,
            weight_kg=75.0,
            ftr=1.20,
            exercise_id=0,
            load_kg=60.0
        )

    _session_active = True
    # Pi feedback fires simultaneously with ESP32
    if _rgb and _rgb.is_enabled:
        _rgb.processing()              # Fast green pulse = session active
    if _buzzer:
        _buzzer.beep_session_start()   # Double beep = session started
    logger.info("Session started (session_id=%s)", _bridge.esp32_session_id)
    return {"session_active": True, "session_id": _bridge.esp32_session_id}


@app.post("/session/stop")
async def session_stop():
    """Stop the session: send 'stop' command to ESP32 and wait for ack."""
    global _session_active
    _session_active = False
    
    if _session_manager:
        _session_manager.stop_session()

    if _rgb and _rgb.is_enabled:
        _rgb.idle()
    if _buzzer:
        _buzzer.beep_session_stop()    # Single low beep = session ended
    logger.info("Session stopped")
    return {"session_active": False}


@app.post("/reconnect/bridge")
async def reconnect_bridge():
    """Disconnect and reconnect the ESP32 MQTT bridge."""
    if _session_manager:
        try:
            _session_manager._imu_bridge.disconnect()
        except Exception:
            pass
        _session_manager._imu_bridge = ESP32Bridge()
        _session_manager._imu_bridge.connect()
        _bridge = _session_manager._imu_bridge
        logger.info("[RECONNECT] Bridge re-initialized (mock=%s)", _bridge.is_mock)
        return {
            "reconnected":   True,
            "is_mock":       _bridge.is_mock,
            "connected":     _bridge.is_connected(),
            "mqtt_enabled":  Config.MQTT.ENABLED,
            "mqtt_broker":   Config.MQTT.BROKER,
        }
    raise HTTPException(status_code=503, detail="SessionManager not initialized")


@app.get("/imu/latest")
async def imu_latest():
    """Return the latest IMU sample from the ESP32 over MQTT."""
    _bridge = _session_manager._imu_bridge if _session_manager else None
    if not _bridge:
        raise HTTPException(status_code=503, detail="ESP32Bridge not initialized")
    sample = _bridge.read_sample()
    return {
        "connected": _bridge.is_connected(),
        "is_mock": _bridge.is_mock,
        "data": sample,
    }

@app.get("/capture")
async def capture_live_state():
    """Return the current combined live state (Vision + IMU) for the dashboard forms."""
    if not _session_manager:
        raise HTTPException(status_code=503, detail="SessionManager not initialized")
    
    imu_sample = _session_manager._imu_bridge.read_sample()
    vision_sample = {}
    angles = {}
    
    fp = _session_manager._frame_processor
    if fp._latest_result and fp._latest_result.is_valid:
        vision_sample = fp._latest_result.landmarks
        angles = fp._latest_result.angles

    return {
        "imu": imu_sample,
        "vision": vision_sample,
        "angles": angles
    }

def generate_mjpeg_frames():
    """Generator for streaming live MJPEG frames from the FrameProcessor.

    When the camera is toggled OFF (demo default) it streams a static
    'Camera Off' placeholder at a low rate instead of live frames.
    """
    # Encode caching: the pose pipeline only produces a new annotated frame at
    # ~pose FPS (~7.5 on a Pi 4), but this generator polls faster. Re-encoding the
    # same frame to JPEG every poll wastes a lot of CPU, so we cache the encoded
    # bytes and only re-encode when the frame actually changes (tracked by the
    # FrameResult timestamp). Big CPU saving, zero visible difference.
    last_ts = None
    cached = None
    while True:
        if not _camera_on:
            # Camera disabled — emit the placeholder slowly (~2 fps).
            if _camera_placeholder_jpeg:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n'
                       + _camera_placeholder_jpeg + b'\r\n')
            last_ts = None
            cached = None
            time.sleep(0.5)
            continue

        if _session_manager and _session_manager._frame_processor:
            result, frame = _session_manager._frame_processor.get_latest()
            if frame is not None:
                ts = result.timestamp_ms if result is not None else None
                if cached is None or ts != last_ts:
                    ok, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ok:
                        cached = buffer.tobytes()
                        last_ts = ts
                if cached is not None:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + cached + b'\r\n')
        time.sleep(0.04)  # ~25fps poll; only re-encodes on new frames (~pose FPS)

@app.get("/video_feed")
async def video_feed():
    """MJPEG streaming endpoint for the dashboard."""
    return StreamingResponse(generate_mjpeg_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for live telemetry data."""
    await websocket.accept()
    _active_websockets.append(websocket)
    try:
        while True:
            # Just keep the connection alive and wait for client messages if any
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        _active_websockets.remove(websocket)

async def _broadcast_live_data():
    """Background task to broadcast fast telemetry data to WebSockets."""
    while True:
        await asyncio.sleep(0.1) # 10Hz broadcast
        if not _active_websockets or not _session_manager:
            continue
            
        fp = _session_manager._frame_processor

        # Telemetry is broadcast independently of the camera. IMU data must NOT
        # be gated on the frame processor — otherwise it only appears when the
        # camera is on. Camera-derived fields (fps/angles/rep_state) are included
        # only when the camera pipeline actually has a result.
        data = {
            "auto_predict": _auto_predict,
            "sensor_on":    _sensor_on,
            "camera_on":    _camera_on,
        }

        if fp and fp._latest_result:
            rep_state = 0
            if getattr(fp, "_rep_segmenter", None):
                rep_state = fp._rep_segmenter.current_phase
            data["fps"]       = fp._latest_result.fps
            data["angles"]    = fp._latest_result.angles
            data["rep_state"] = rep_state

        # IMU streams whenever a session is active and the sensor is not paused —
        # regardless of the camera.
        if _session_active and _sensor_on and _session_manager._imu_bridge:
            data["imu"] = _session_manager._imu_bridge.read_sample()

        payload = {"type": "telemetry", "data": data}

        dead_sockets = []
        for ws in _active_websockets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead_sockets.append(ws)
        for ws in dead_sockets:
            _active_websockets.remove(ws)


@app.post("/predict")
async def predict(request: PredictionRequest):
    """Run v4 inference on 3 phases of input data.

    Assembles the 40-feature vectors, computes the delta row (phase3 - phase1),
    runs winsorize → impute → scale preprocessing, then feeds the (4, 40)
    sequence to LSTMRunner. Fires buzzer on bad form detection.

    Returns:
        JSON with label, confidence, probability, latency, buzzer_fired flag.
    """
    _runner = _session_manager._lstm_runner if _session_manager else None
    if not _runner or not _runner.is_loaded():
        raise HTTPException(status_code=503, detail="Model not loaded")

    if _rgb and _rgb.is_enabled:
        _rgb.processing()

    start_time = time.perf_counter()

    # Build (3, 40) raw feature matrix from the 3 phases
    raw_phases = []
    for phase in request.phases:
        bmi = request.subject.weight_kg / ((request.subject.height_cm / 100.0) ** 2)

        # Compute engineered features if not provided
        acc_mag = phase.imu_acc_magnitude
        if acc_mag is None:
            acc_mag = float(np.sqrt(
                phase.imu_acc_x**2 + phase.imu_acc_y**2 + phase.imu_acc_z**2
            ))

        # Knee-hip coupling: knee_angle * hip_y (proxy for depth-load coupling)
        khc_l = phase.knee_hip_coupling_l
        if khc_l is None:
            khc_l = phase.vis_l_knee_y * phase.vis_l_hip_y

        khc_r = phase.knee_hip_coupling_r
        if khc_r is None:
            khc_r = phase.vis_r_knee_y * phase.vis_r_hip_y

        vdr = phase.velocity_decel_ratio
        if vdr is None:
            vdr = 1.0  # placeholder — real value computed after all phases

        # Assemble in EXACT FEATURE_ORDER
        feature_vec = [
            request.subject.height_cm,               # Subject_Height_cm
            request.subject.weight_kg,                # Subject_Weight_kg
            float(request.session.exercise_id),       # Exercise_ID
            float(phase.rep_phase),                   # Rep_Phase
            request.session.load_kg,                  # Load_kg
            phase.vis_l_shoulder_x,                   # Vis_L_Shoulder_X
            phase.vis_l_shoulder_y,                   # Vis_L_Shoulder_Y
            phase.vis_r_shoulder_x,                   # Vis_R_Shoulder_X
            phase.vis_r_shoulder_y,                   # Vis_R_Shoulder_Y
            phase.vis_l_hip_x,                        # Vis_L_Hip_X
            phase.vis_l_hip_y,                        # Vis_L_Hip_Y
            phase.vis_r_hip_x,                        # Vis_R_Hip_X
            phase.vis_r_hip_y,                        # Vis_R_Hip_Y
            phase.vis_l_knee_x,                       # Vis_L_Knee_X
            phase.vis_l_knee_y,                       # Vis_L_Knee_Y
            phase.vis_r_knee_x,                       # Vis_R_Knee_X
            phase.vis_r_knee_y,                       # Vis_R_Knee_Y
            phase.vis_l_ankle_x,                      # Vis_L_Ankle_X
            phase.vis_l_ankle_y,                      # Vis_L_Ankle_Y
            phase.vis_r_ankle_x,                      # Vis_R_Ankle_X
            phase.vis_r_ankle_y,                      # Vis_R_Ankle_Y
            phase.angle_trunk_inclination,            # Angle_Trunk_Inclination
            phase.imu_acc_x,                          # IMU_Acc_X
            phase.imu_acc_y,                          # IMU_Acc_Y
            phase.imu_acc_z,                          # IMU_Acc_Z
            phase.imu_gyro_x,                         # IMU_Gyro_X
            phase.imu_gyro_y,                         # IMU_Gyro_Y
            phase.imu_gyro_z,                         # IMU_Gyro_Z
            phase.v_bar_velocity_vertical,            # V_Bar_Velocity_Vertical
            phase.p_bar_power_watts,                  # P_Bar_Power_Watts
            phase.smoothness_jerk,                    # Smoothness_Jerk
            phase.hip_flexion_asymmetry,              # Hip_Flexion_Asymmetry
            phase.knee_flexion_asymmetry,             # Knee_Flexion_Asymmetry
            phase.ankle_dorsiflexion_asymmetry,       # Ankle_Dorsiflexion_Asymmetry
            acc_mag,                                  # IMU_Acc_Magnitude
            khc_l,                                    # Knee_Hip_Coupling_L
            khc_r,                                    # Knee_Hip_Coupling_R
            vdr,                                      # Velocity_Decel_Ratio
            request.subject.femur_tibia_ratio,        # Femur_Tibia_Ratio
            bmi,                                      # BMI
        ]
        raw_phases.append(feature_vec)

    # Stack to (3, 40)
    X_raw = np.array(raw_phases, dtype=np.float32)

    # Compute real Velocity_Decel_Ratio now that all phases are available
    vdr_idx = FEATURE_ORDER.index("Velocity_Decel_Ratio")
    vel_idx = FEATURE_ORDER.index("V_Bar_Velocity_Vertical")
    phase1_vel = X_raw[0, vel_idx]
    phase3_vel = X_raw[2, vel_idx]
    real_vdr = phase3_vel / (abs(phase1_vel) + 1e-6)
    X_raw[:, vdr_idx] = real_vdr

    # Compute delta row (phase3 - phase1) — this is the 4th timestep
    delta = X_raw[2] - X_raw[0]
    X_model = np.vstack([X_raw, delta.reshape(1, -1)])  # (4, 40)

    # Run inference (LSTMRunner handles preprocessing internally)
    result = _runner.predict(X_model)

    elapsed_ms = (time.perf_counter() - start_time) * 1000

    # Fire buzzer, LED and publish result to ESP32
    buzzer_fired = False
    _bridge = _session_manager._imu_bridge if _session_manager else None
    
    if result.is_bad_form:
        if _buzzer and _buzzer.is_enabled:
            _buzzer.beep_bad_form()    # Pi buzzer fires simultaneously
            buzzer_fired = True
        if _rgb and _rgb.is_enabled:
            _rgb.bad_form()
        if _bridge:
            _bridge.publish_result(True, result.confidence)  # → ESP32 buzzer
        logger.info("🔴 BAD FORM detected (%.1f%%)", result.confidence * 100)
    else:
        if _rgb and _rgb.is_enabled:
            _rgb.good_form()
        if _buzzer and _buzzer.is_enabled:
            _buzzer.beep_good_form()   # Pi buzzer fires simultaneously
        if _bridge:
            _bridge.publish_result(False, result.confidence) # → ESP32 buzzer
        logger.info("🟢 %s (%.1f%%)", result.label, result.confidence * 100)

    return {
        "label": result.label,
        "confidence": round(result.confidence * 100, 1),
        "probability": {
            "good_form": round((1.0 - result.confidence) * 100, 1),
            "bad_form": round(result.confidence * 100, 1),
        },
        "is_bad_form": result.is_bad_form,
        "threshold": Config.INFERENCE.DECISION_THRESHOLD,
        "latency_ms": round(elapsed_ms, 2),
        "is_mock": result.is_mock,
        "buzzer_fired": buzzer_fired,
    }


@app.post("/buzzer/test")
async def buzzer_test():
    """Fire a single test beep to verify buzzer hardware."""
    if not _buzzer:
        raise HTTPException(status_code=503, detail="Buzzer not initialized")
    _buzzer.beep_test()
    return {
        "status": "beeped",
        "pin": Config.BUZZER.GPIO_PIN,
        "is_mock": _buzzer.is_mock,
    }


@app.post("/buzzer/bad-form")
async def buzzer_bad_form():
    """Fire the full bad-form triple beep pattern."""
    if not _buzzer:
        raise HTTPException(status_code=503, detail="Buzzer not initialized")
    _buzzer.beep_bad_form()
    return {
        "status": "triple_beep",
        "pattern": Config.BUZZER.BAD_FORM_PATTERN,
        "is_mock": _buzzer.is_mock,
    }


@app.post("/rgb/test")
async def rgb_test(color: str = "white"):
    """Test RGB LED colors. Valid colors: red, green, blue, amber, cyan, purple, white, off, idle, processing, bad_form, good_form"""
    if not _rgb:
        raise HTTPException(status_code=503, detail="RGB not initialized")
    
    color = color.lower()
    if color == "red": _rgb.set_color(_rgb.RED)
    elif color == "green": _rgb.set_color(_rgb.GREEN)
    elif color == "blue": _rgb.set_color(_rgb.BLUE)
    elif color == "amber": _rgb.set_color(_rgb.AMBER)
    elif color == "cyan": _rgb.set_color(_rgb.CYAN)
    elif color == "purple": _rgb.set_color(_rgb.PURPLE)
    elif color == "white": _rgb.set_color(_rgb.WHITE)
    elif color == "off": _rgb.off()
    elif color == "idle": _rgb.idle()
    elif color == "processing": _rgb.processing()
    elif color == "bad_form": _rgb.bad_form()
    elif color == "good_form": _rgb.good_form()
    else: raise HTTPException(status_code=400, detail="Invalid color")
    
    return {
        "status": "color_set",
        "color": color,
        "is_mock": _rgb.is_mock,
    }


@app.get("/feature-order")
async def feature_order():
    """Return the exact feature order for debugging."""
    return {
        "feature_order": FEATURE_ORDER,
        "total_features": TOTAL_FEATURES,
        "sequence_length": SEQUENCE_LENGTH_MODEL,
    }


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("Digital Spotter — Production Dashboard (v4 BiLSTM+MHA)")
    print(f"Features: {TOTAL_FEATURES} × {SEQUENCE_LENGTH_MODEL} timesteps")
    print(f"Threshold: {Config.INFERENCE.DECISION_THRESHOLD}")
    print(f"Buzzer: GPIO {Config.BUZZER.GPIO_PIN} ({'enabled' if Config.BUZZER.ENABLED else 'disabled'})")
    print(f"RGB LED: GPIO {Config.RGB_LED.PIN_R},{Config.RGB_LED.PIN_G},{Config.RGB_LED.PIN_B} ({'enabled' if Config.RGB_LED.ENABLED else 'disabled'})")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
