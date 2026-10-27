"""
Gym Fusion Model Inference Backend - FastAPI
Loads LSTM and Random Forest models for real-time exercise form prediction
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import numpy as np
import joblib
import tensorflow as tf
from typing import List, Dict, Any
import logging
import webbrowser
import threading
import time
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models for request validation
class SubjectInfo(BaseModel):
    height_cm: float
    weight_kg: float
    femur_tibia_ratio: float

class SessionInfo(BaseModel):
    exercise_id: int
    load_kg: float

class PhaseData(BaseModel):
    rep_phase: int
    # Vision joints (16)
    vis_l_shoulder_x: float
    vis_l_shoulder_y: float
    vis_r_shoulder_x: float
    vis_r_shoulder_y: float
    vis_l_hip_x: float
    vis_l_hip_y: float
    vis_r_hip_x: float
    vis_r_hip_y: float
    vis_l_knee_x: float
    vis_l_knee_y: float
    vis_r_knee_x: float
    vis_r_knee_y: float
    vis_l_ankle_x: float
    vis_l_ankle_y: float
    vis_r_ankle_x: float
    vis_r_ankle_y: float
    # Angles (7: 4 means + 3 asymmetries)
    angle_trunk_inclination: float
    angle_hip_flexion_mean: float
    hip_flexion_asymmetry: float
    angle_knee_flexion_mean: float
    knee_flexion_asymmetry: float
    angle_ankle_dorsiflexion_mean: float
    ankle_dorsiflexion_asymmetry: float
    # IMU (6)
    imu_acc_x: float
    imu_acc_y: float
    imu_acc_z: float
    imu_gyro_x: float
    imu_gyro_y: float
    imu_gyro_z: float
    # Performance (3)
    v_bar_velocity_vertical: float
    p_bar_power_watts: float
    smoothness_jerk: float

class PredictionRequest(BaseModel):
    subject: SubjectInfo
    session: SessionInfo
    phases: List[PhaseData]

# Initialize FastAPI app
app = FastAPI(
    title="Gym Fusion - Exercise Form Prediction API",
    description="Real-time gym exercise form quality prediction",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global model storage
models = {
    "lstm": None,
    "random_forest": None,
    "scaler": None
}

@app.on_event("startup")
async def load_models():
    """Load pre-trained models at startup"""
    try:
        logger.info("Loading models from Datasets v2/saved_models/...")

        # Load LSTM model
        models["lstm"] = tf.keras.models.load_model("Datasets v2/saved_models/best_lstm_checkpoint.keras")
        logger.info("✓ LSTM model loaded")

        # Load Random Forest model
        models["random_forest"] = joblib.load("Datasets v2/saved_models/random_forest_model.joblib")
        logger.info("✓ Random Forest model loaded")

        # Load scaler
        models["scaler"] = joblib.load("Datasets v2/saved_models/scaler.save")
        logger.info("✓ Scaler loaded")

        logger.info("All models loaded successfully!")

    except FileNotFoundError as e:
        logger.error(f"Model file not found: {e}")
        logger.warning("Models will be unavailable. Ensure Datasets v2/saved_models/ contains: best_lstm_checkpoint.keras, random_forest_model.joblib, scaler.save")
    except Exception as e:
        logger.error(f"Error loading models: {e}")
        raise

    # Open browser automatically
    def open_browser():
        time.sleep(1)  # Give server time to start
        index_path = os.path.join(os.path.dirname(__file__), "index.html")
        if os.path.exists(index_path):
            webbrowser.open(f"file://{os.path.abspath(index_path)}")
            logger.info("✓ Opening index.html in browser")
        else:
            webbrowser.open("http://localhost:8000/")
            logger.info("✓ Opening http://localhost:8000/ in browser")

    threading.Thread(target=open_browser, daemon=True).start()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    models_loaded = all(v is not None for v in models.values())
    status = "healthy" if models_loaded else "degraded"
    return {
        "status": status,
        "models_loaded": models_loaded,
        "available_models": {
            "lstm": models["lstm"] is not None,
            "random_forest": models["random_forest"] is not None,
            "scaler": models["scaler"] is not None
        }
    }

@app.post("/predict")
async def predict(request: PredictionRequest) -> Dict[str, Any]:
    """
    Predict exercise form quality using both LSTM and Random Forest models
    """

    if not all([models["lstm"], models["random_forest"], models["scaler"]]):
        raise HTTPException(status_code=503, detail="Models not loaded. Check server logs.")

    try:
        # Extract features in the EXACT order of FEATURE_COLS from notebook
        features = []
        for phase in request.phases:
            phase_features = [
                # Context / Subject (5)
                request.subject.height_cm,
                request.subject.weight_kg,
                float(request.session.exercise_id),
                float(phase.rep_phase),
                request.session.load_kg,
                
                # Vision Joints (16)
                phase.vis_l_shoulder_x,
                phase.vis_l_shoulder_y,
                phase.vis_r_shoulder_x,
                phase.vis_r_shoulder_y,
                phase.vis_l_hip_x,
                phase.vis_l_hip_y,
                phase.vis_r_hip_x,
                phase.vis_r_hip_y,
                phase.vis_l_knee_x,
                phase.vis_l_knee_y,
                phase.vis_r_knee_x,
                phase.vis_r_knee_y,
                phase.vis_l_ankle_x,
                phase.vis_l_ankle_y,
                phase.vis_r_ankle_x,
                phase.vis_r_ankle_y,
                
                # Trunk Angle (1)
                phase.angle_trunk_inclination,
                
                # IMU (6)
                phase.imu_acc_x,
                phase.imu_acc_y,
                phase.imu_acc_z,
                phase.imu_gyro_x,
                phase.imu_gyro_y,
                phase.imu_gyro_z,
                
                # Performance (3)
                phase.v_bar_velocity_vertical,
                phase.p_bar_power_watts,
                phase.smoothness_jerk,
                
                # Engineered Angles (6)
                phase.angle_hip_flexion_mean,
                phase.hip_flexion_asymmetry,
                phase.angle_knee_flexion_mean,
                phase.knee_flexion_asymmetry,
                phase.angle_ankle_dorsiflexion_mean,
                phase.ankle_dorsiflexion_asymmetry,
                
                # Meta Ratio (1)
                request.subject.femur_tibia_ratio,
            ]
            features.append(phase_features)

        # Create numpy array (3, 38)
        X = np.array(features, dtype=np.float32)

        # Scale features - Scaler expects same order as fit()
        X_scaled = models["scaler"].transform(X)

        # LSTM prediction: (1, 3, 38)
        X_lstm = X_scaled.reshape(1, 3, 38)
        lstm_pred = models["lstm"].predict(X_lstm, verbose=0)
        lstm_prob_bad = float(lstm_pred[0][0])
        lstm_prob_good = 1.0 - lstm_prob_bad
        lstm_label = "Bad Form" if lstm_prob_bad >= 0.5 else "Good Form"
        lstm_confidence = max(lstm_prob_good, lstm_prob_bad)

        # RF prediction: (1, 114)
        X_rf = X_scaled.reshape(1, -1)
        rf_probs = models["random_forest"].predict_proba(X_rf)[0]
        rf_prob_bad = float(rf_probs[1])
        rf_prob_good = float(rf_probs[0])
        rf_label = "Bad Form" if rf_prob_bad >= 0.5 else "Good Form"
        rf_confidence = max(rf_prob_good, rf_prob_bad)

        models_agree = lstm_label == rf_label

        return {
            "lstm": {
                "label": lstm_label,
                "confidence": round(lstm_confidence * 100, 1),
                "probability": {
                    "good_form": round(lstm_prob_good * 100, 1),
                    "bad_form": round(lstm_prob_bad * 100, 1)
                }
            },
            "random_forest": {
                "label": rf_label,
                "confidence": round(rf_confidence * 100, 1),
                "probability": {
                    "good_form": round(rf_prob_good * 100, 1),
                    "bad_form": round(rf_prob_bad * 100, 1)
                }
            },
            "agreement": {
                "models_agree": models_agree,
                "consensus": lstm_label if models_agree else None
            }
        }

    except Exception as e:
        logger.error(f"Prediction error: {e}")
        raise HTTPException(status_code=400, detail=f"Prediction failed: {str(e)}")

@app.get("/")
async def root():
    return {"name": "Gym Fusion API", "status": "active"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)