"""Open-Meteo API ingestion client for Sarawak assets."""

from __future__ import annotations
import requests
from hydrogrid.config import Settings

# Bakun Dam Coordinates (Approximate)
BAKUN_LAT = 2.8825
BAKUN_LON = 114.0614

def fetch_telemetry(
    settings: Settings,
    latitude: float,
    longitude: float,
    timezone: str = "Asia/Kuching",
    hourly_metrics: str = "temperature_2m,relative_humidity_2m,precipitation,global_tilted_irradiance",
    forecast_days: int = 1,
) -> dict:
    """Fetches weather and solar irradiance telemetry from Open-Meteo for arbitrary coordinates.
    
    Args:
        settings: Validated application settings.
        latitude: Geographic latitude.
        longitude: Geographic longitude.
        timezone: Target timezone name (default: Asia/Kuching).
        hourly_metrics: Comma-separated list of hourly metrics.
        forecast_days: Number of forecast days (default: 1).
        
    Returns:
        dict: The JSON response from Open-Meteo containing hourly telemetry.
        
    Raises:
        requests.exceptions.HTTPError: If the API returns a non-200 status code.
    """
    url = f"{settings.openmeteo_base_url.rstrip('/')}/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": hourly_metrics,
        "timezone": timezone,
        "forecast_days": forecast_days,
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_bakun_telemetry(settings: Settings) -> dict:
    """Fetches current weather and solar irradiance telemetry for Bakun Dam.
    
    Args:
        settings: Validated application settings.
        
    Returns:
        dict: The JSON response from Open-Meteo containing hourly telemetry.
        
    Raises:
        requests.exceptions.HTTPError: If the API returns a non-200 status code.
    """
    return fetch_telemetry(
        settings=settings,
        latitude=BAKUN_LAT,
        longitude=BAKUN_LON,
        timezone="Asia/Kuching",
    )