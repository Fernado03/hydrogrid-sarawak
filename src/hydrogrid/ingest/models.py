"""Pydantic data contracts for Open-Meteo API responses."""

from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field

class OpenMeteoHourlyData(BaseModel):
    """Validates the nested 'hourly' arrays from Open-Meteo."""
    
    time: list[datetime]
    temperature_2m: list[float | None]
    relative_humidity_2m: list[float | None]
    precipitation: list[float | None]
    global_tilted_irradiance: list[float | None]

class OpenMeteoResponse(BaseModel):
    """Validates the top-level API response."""
    
    hourly: OpenMeteoHourlyData
    timezone: str