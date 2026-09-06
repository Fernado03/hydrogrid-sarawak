"""FastAPI operational inference microservice for HydroGrid Sarawak."""

from __future__ import annotations
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, status
from lightgbm import LGBMRegressor
from sklearn.ensemble import IsolationForest

from hydrogrid.ml.anomaly import ANOMALY_FEATURE_COLUMNS
from hydrogrid.ml.train import FEATURE_COLUMNS
from hydrogrid.serving.schemas import (
    AnomalyCheckRequest,
    AnomalyCheckResponse,
    HealthResponse,
    InflowPredictionRequest,
    InflowPredictionResponse,
)

# Application state container for in-memory model singletons
models: Dict[str, Any] = {
    "inflow_forecaster": None,
    "anomaly_detector": None,
}

MODEL_DIR = Path(os.getenv("MODEL_DIR", "models"))
INFLOW_MODEL_PATH = MODEL_DIR / "inflow_model.joblib"
ANOMALY_MODEL_PATH = MODEL_DIR / "anomaly_detector.joblib"


def _create_baseline_inflow_model() -> LGBMRegressor:
    """Trains a baseline fallback regressor if no serialized artifact exists on disk."""
    X = pd.DataFrame({
        "hour_sin": [0.0, 0.707, 1.0, 0.0, -0.707, -1.0],
        "hour_cos": [1.0, 0.707, 0.0, -1.0, -0.707, 0.0],
        "temperature_2m": [25.0, 27.0, 30.0, 28.0, 26.0, 24.0],
        "precipitation_lag_1h": [0.0, 2.0, 15.0, 25.0, 5.0, 0.0],
        "precipitation_lag_24h": [10.0, 15.0, 45.0, 60.0, 20.0, 5.0],
        "temp_lag_1h": [24.5, 26.5, 29.5, 27.5, 25.5, 23.5],
    })[FEATURE_COLUMNS]
    y = np.array([210.0, 245.0, 520.0, 780.0, 390.0, 225.0])
    model = LGBMRegressor(n_estimators=25, random_state=42, verbose=-1)
    model.fit(X, y)
    return model


def _create_baseline_anomaly_detector() -> IsolationForest:
    """Trains a baseline Isolation Forest detector if no artifact exists on disk."""
    X = pd.DataFrame({
        "temperature_2m": [24.0, 28.0, 31.0, 26.0, 29.0, 27.5],
        "relative_humidity_2m": [70.0, 80.0, 85.0, 90.0, 75.0, 82.0],
        "precipitation": [0.0, 5.0, 20.0, 0.0, 2.0, 12.0],
        "global_tilted_irradiance": [0.0, 450.0, 800.0, 0.0, 600.0, 350.0],
    })[ANOMALY_FEATURE_COLUMNS]
    detector = IsolationForest(contamination=0.05, random_state=42)
    detector.fit(X)
    return detector


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages model lifecycle, pre-loading artifacts into memory on startup."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load or initialize Inflow Forecasting model
    if INFLOW_MODEL_PATH.exists():
        models["inflow_forecaster"] = joblib.load(INFLOW_MODEL_PATH)
    else:
        models["inflow_forecaster"] = _create_baseline_inflow_model()
        joblib.dump(models["inflow_forecaster"], INFLOW_MODEL_PATH)

    # 2. Load or initialize Anomaly Detection model
    if ANOMALY_MODEL_PATH.exists():
        models["anomaly_detector"] = joblib.load(ANOMALY_MODEL_PATH)
    else:
        models["anomaly_detector"] = _create_baseline_anomaly_detector()
        joblib.dump(models["anomaly_detector"], ANOMALY_MODEL_PATH)

    yield
    models.clear()


app = FastAPI(
    title="HydroGrid Sarawak Inference API",
    description="Operational telemetry anomaly detection and hydro inflow forecasting service.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Returns service health status and confirms whether models are loaded."""
    return HealthResponse(
        status="healthy",
        inflow_model_loaded=models.get("inflow_forecaster") is not None,
        anomaly_model_loaded=models.get("anomaly_detector") is not None,
    )


@app.post("/predict/inflow", response_model=InflowPredictionResponse)
async def predict_inflow(payload: InflowPredictionRequest) -> InflowPredictionResponse:
    """Predicts catchment inflow (m³/s) using the trained LightGBM model."""
    model = models.get("inflow_forecaster")
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Inflow forecaster model is not loaded.",
        )

    hour = payload.timestamp.hour
    hour_sin = float(np.sin(2.0 * np.pi * hour / 24.0))
    hour_cos = float(np.cos(2.0 * np.pi * hour / 24.0))

    feature_df = pd.DataFrame([{
        "hour_sin": hour_sin,
        "hour_cos": hour_cos,
        "temperature_2m": payload.temperature_2m,
        "precipitation_lag_1h": payload.precipitation_lag_1h,
        "precipitation_lag_24h": payload.precipitation_lag_24h,
        "temp_lag_1h": payload.temp_lag_1h,
    }])[FEATURE_COLUMNS]

    prediction = model.predict(feature_df)[0]

    return InflowPredictionResponse(
        predicted_inflow_m3s=round(float(prediction), 2),
        model_version="lgbm-v1",
    )


@app.post("/detect/anomaly", response_model=AnomalyCheckResponse)
async def detect_anomaly(payload: AnomalyCheckRequest) -> AnomalyCheckResponse:
    """Evaluates telemetry record against the Isolation Forest detector."""
    detector = models.get("anomaly_detector")
    if detector is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Anomaly detector model is not loaded.",
        )

    input_df = pd.DataFrame([{
        "temperature_2m": payload.temperature_2m,
        "relative_humidity_2m": payload.relative_humidity_2m,
        "precipitation": payload.precipitation,
        "global_tilted_irradiance": payload.global_tilted_irradiance,
    }])[ANOMALY_FEATURE_COLUMNS]

    pred_label = detector.predict(input_df)
    score = detector.decision_function(input_df)
    is_anomaly = bool(pred_label[0] == -1)

    return AnomalyCheckResponse(
        is_anomaly=is_anomaly,
        anomaly_score=round(float(score[0]), 4),
        sensor_status="WARNING_OUTLIER" if is_anomaly else "NORMAL",
    )

# At the bottom of src/hydrogrid/serving/app.py

@app.post("/ingest/run")
def trigger_telemetry_ingestion():
    import json
    import os
    import urllib.request
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    user = os.getenv("POSTGRES_USER", "hydrogrid")
    password = os.getenv("POSTGRES_PASSWORD", "change_me")
    host = os.getenv("POSTGRES_HOST", "db")
    port = os.getenv("POSTGRES_PORT", "5432")
    dbname = os.getenv("POSTGRES_DB", "hydrogrid_warehouse")

    engine = create_engine(f"postgresql://{user}:{password}@{host}:{port}/{dbname}")

    assets = [
        ("Bakun Dam", 2.75, 114.05),
        ("Murum Dam", 2.65, 114.30),
        ("Batang Ai", 1.15, 111.90),
        ("Bintulu H2 Hub", 3.20, 113.05),
    ]

    total_upserted = 0

    with Session(engine) as session:
        for name, lat, lon in assets:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,relative_humidity_2m,precipitation,global_tilted_irradiance&forecast_days=7"
            req = urllib.request.Request(url, headers={"User-Agent": "HydroGrid/1.0"})
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])
            hums = hourly.get("relative_humidity_2m", [])
            precips = hourly.get("precipitation", [])
            gtis = hourly.get("global_tilted_irradiance", [])

            res = session.execute(
                text("SELECT id FROM warehouse.dim_asset WHERE asset_name = :name"),
                {"name": name},
            ).fetchone()
            if not res:
                continue
            asset_id = res[0]

            insert_sql = text("""
                INSERT INTO warehouse.fact_telemetry (
                    asset_id, timestamp, temperature_2m, relative_humidity_2m, precipitation, global_tilted_irradiance
                ) VALUES (
                    :asset_id, :ts, :temp, :hum, :precip, :gti
                )
                ON CONFLICT (asset_id, timestamp) DO UPDATE SET
                    temperature_2m = EXCLUDED.temperature_2m,
                    relative_humidity_2m = EXCLUDED.relative_humidity_2m,
                    precipitation = EXCLUDED.precipitation,
                    global_tilted_irradiance = EXCLUDED.global_tilted_irradiance;
            """)

            records = [
                {
                    "asset_id": asset_id,
                    "ts": times[i],
                    "temp": temps[i],
                    "hum": hums[i],
                    "precip": precips[i],
                    "gti": gtis[i],
                }
                for i in range(len(times))
            ]
            session.execute(insert_sql, records)
            total_upserted += len(records)
            session.commit()

        session.execute(text("TRUNCATE TABLE marts.daily_telemetry_summary;"))
        session.execute(text("""
            INSERT INTO marts.daily_telemetry_summary (asset_id, summary_date, avg_temp, total_precip, max_irradiance)
            SELECT 
                asset_id,
                DATE(timestamp) AS summary_date,
                ROUND(AVG(temperature_2m)::numeric, 2),
                ROUND(SUM(precipitation)::numeric, 2),
                ROUND(MAX(global_tilted_irradiance)::numeric, 2)
            FROM warehouse.fact_telemetry
            GROUP BY asset_id, DATE(timestamp);
        """))
        session.commit()

    return {
        "status": "SUCCESS",
        "assets_processed": len(assets),
        "total_records_upserted": total_upserted,
        "mart_refreshed": True,
    }