"""Verification tests for HydroGrid Sarawak database connectivity."""

from __future__ import annotations
import pytest
from sqlalchemy import text

from hydrogrid.config import load_settings
from hydrogrid.db.engine import get_postgres_engine


def test_postgres_connection_live() -> None:
    """Test that we can connect to the local Dockerized PostgreSQL instance."""
    
    # We inject a test dictionary to strictly adhere to our design principles.
    # Ensure these values match what you put in your docker-compose.yml!
    test_env = {
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
    
    settings = load_settings(test_env)
    
    engine = get_postgres_engine(settings)
    
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1