"""Verification tests for HydroGrid Sarawak schema separation."""

from __future__ import annotations
import pytest
from sqlalchemy import text

from hydrogrid.config import load_settings
from hydrogrid.db.engine import get_postgres_engine
from hydrogrid.db.schema_setup import setup_schemas


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


def test_schemas_are_created_successfully() -> None:
    """Test that the setup script creates all required warehouse schemas."""
    settings = load_settings(TEST_ENV)
    engine = get_postgres_engine(settings)
    
    # Run your setup function
    setup_schemas(engine)
    
    # Query PostgreSQL to see what schemas exist
    query = text("SELECT schema_name FROM information_schema.schemata;")
    with engine.connect() as conn:
        result = conn.execute(query)
        # Extract the schema names into a simple list
        db_schemas = [row[0] for row in result]
        
    # Verify our custom schemas are in the database
    expected_schemas = ["raw", "staging", "warehouse", "marts"]
    for schema in expected_schemas:
        assert schema in db_schemas, f"Expected schema '{schema}' not found in the database."