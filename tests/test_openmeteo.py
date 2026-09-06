"""Verification tests for Open-Meteo ingestion client."""

from __future__ import annotations
import pytest

from hydrogrid.config import load_settings
from hydrogrid.ingest.openmeteo import fetch_bakun_telemetry

TEST_ENV = {
    "HYDROGRID_ENV": "test",
    "POSTGRES_HOST": "localhost", 
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "hydrogrid_warehouse",
    "POSTGRES_USER": "hydrogrid",
    "POSTGRES_PASSWORD": "change_me", 
    "OPEN_METEO_BASE_URL": "https://api.open-meteo.com",
    "LLM_BASE_URL": "https://llm.example.com/v1",
    "LLM_API_KEY": "test-key"
}

def test_bakun_telemetry_payload_structure() -> None:
    """Test that we successfully fetch expected telemetry keys from Open-Meteo."""
    settings = load_settings(TEST_ENV)
    
    # Execute the ingestion function
    data = fetch_bakun_telemetry(settings)
    
    # Verify the API returned the expected top-level structure
    assert "hourly" in data, "Open-Meteo response missing 'hourly' key."
    assert "Asia/Kuching" in data.get("timezone", ""), "Timezone mismatch!"

    hourly_data = data["hourly"]
    
    # TODO 2: Add assertions to verify that the hourly_data dictionary contains 
    # the specific telemetry keys we requested in our parameters.
    # We need to ensure we got: "time", "temperature_2m", "precipitation", and "global_tilted_irradiance".
    expected_metrics = [
        "time",
        "temperature_2m",
        "relative_humidity_2m",
        "precipitation",
        "global_tilted_irradiance"
    ]

    for metric in expected_metrics:
        assert metric in hourly_data, f"Missing expected telemetry metric: '{metric}'"
    
