"""Pydantic schemas for the HydroGrid Inference API."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class InflowPredictionRequest(BaseModel):
    """Payload for predicting catchment inflow rate."""
    timestamp: datetime = Field(..., description="Observation timestamp (UTC or local with offset)")
    temperature_2m: float = Field(..., description="Ambient temperature at 2m in Celsius")
    precipitation_lag_1h: float = Field(..., ge=0.0, description="Precipitation 1 hour prior (mm)")
    precipitation_lag_24h: float = Field(..., ge=0.0, description="Precipitation 24 hours prior (mm)")
    temp_lag_1h: float = Field(..., description="Temperature 1 hour prior in Celsius")


class InflowPredictionResponse(BaseModel):
    """Response containing predicted inflow rate."""
    predicted_inflow_m3s: float
    model_version: str
    processed_at: datetime = Field(default_factory=datetime.utcnow)


class AnomalyCheckRequest(BaseModel):
    """Payload for sensor anomaly evaluation."""
    temperature_2m: float
    relative_humidity_2m: float = Field(..., ge=0.0, le=100.0)
    precipitation: float = Field(..., ge=0.0)
    global_tilted_irradiance: float = Field(..., ge=0.0)


class AnomalyCheckResponse(BaseModel):
    """Response containing anomaly evaluation and health score."""
    is_anomaly: bool
    anomaly_score: float
    sensor_status: str


class HealthResponse(BaseModel):
    """Service health and loaded model status."""
    status: str
    inflow_model_loaded: bool
    anomaly_model_loaded: bool