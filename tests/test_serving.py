"""Verification tests for FastAPI inference microservice."""

from __future__ import annotations
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from lightgbm import LGBMRegressor
from sklearn.ensemble import IsolationForest

from hydrogrid.serving.app import app, models


@pytest.fixture(scope="module")
def client():
    """Provides a TestClient with fitted mock model instances injected into app state."""
    # Fit minimal LightGBM model with at least 2 samples
    lgbm = LGBMRegressor(n_estimators=5, random_state=42)
    X_lgbm = [
        [0.5, 0.5, 26.0, 1.0, 5.0, 25.5],
        [0.4, 0.6, 27.0, 2.0, 6.0, 26.0],
    ]
    y_lgbm = [120.0, 130.0]
    lgbm.fit(X_lgbm, y_lgbm)

    # Fit minimal IsolationForest model
    iso = IsolationForest(n_estimators=10, random_state=42)
    X_iso = [
        [25.0, 80.0, 0.0, 300.0],
        [26.0, 82.0, 1.0, 320.0],
        [27.0, 85.0, 0.5, 310.0],
    ]
    iso.fit(X_iso)

    # Inject models into app state
    models["inflow_forecaster"] = lgbm
    models["anomaly_detector"] = iso

    with TestClient(app) as test_client:
        yield test_client

    models["inflow_forecaster"] = None
    models["anomaly_detector"] = None


def test_health_check_endpoint(client: TestClient):
    """Verify /health reports all systems healthy and models loaded."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["inflow_model_loaded"] is True
    assert data["anomaly_model_loaded"] is True


def test_predict_inflow_success(client: TestClient):
    """Verify /predict/inflow handles valid payload and returns predicted inflow."""
    payload = {
        "timestamp": "2026-03-30T14:00:00Z",
        "temperature_2m": 28.5,
        "precipitation_lag_1h": 2.0,
        "precipitation_lag_24h": 15.0,
        "temp_lag_1h": 28.0,
    }
    response = client.post("/predict/inflow", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "predicted_inflow_m3s" in data
    assert isinstance(data["predicted_inflow_m3s"], float)
    assert data["model_version"] == "lgbm-v1"


def test_predict_inflow_validation_error(client: TestClient):
    """Verify /predict/inflow rejects negative precipitation with 422 Unprocessable Entity."""
    payload = {
        "timestamp": "2026-03-30T14:00:00Z",
        "temperature_2m": 28.5,
        "precipitation_lag_1h": -5.0,  # Violates ge=0.0 constraint
        "precipitation_lag_24h": 15.0,
        "temp_lag_1h": 28.0,
    }
    response = client.post("/predict/inflow", json=payload)
    assert response.status_code == 422


def test_detect_anomaly_endpoint(client: TestClient):
    """Verify /detect/anomaly responds with evaluation and sensor status."""
    payload = {
        "temperature_2m": 26.5,
        "relative_humidity_2m": 82.0,
        "precipitation": 0.5,
        "global_tilted_irradiance": 315.0,
    }
    response = client.post("/detect/anomaly", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "is_anomaly" in data
    assert "anomaly_score" in data
    assert data["sensor_status"] in ["NORMAL", "WARNING_OUTLIER"]