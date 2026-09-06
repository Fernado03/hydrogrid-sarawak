"""Verification tests for the Open-Meteo ETL Pipeline."""

from __future__ import annotations
from datetime import datetime
import pytest
from sqlalchemy.orm import sessionmaker

from hydrogrid.config import load_settings
from hydrogrid.db.engine import get_postgres_engine
from hydrogrid.db.base import Base
from hydrogrid.db.models import RawOpenMeteo
from hydrogrid.ingest.openmeteo import fetch_bakun_telemetry
# TODO 1: Import transform_and_load_bakun_telemetry
from hydrogrid.ingest.pipeline import transform_and_load_bakun_telemetry

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

@pytest.fixture(scope="function")
def db_session():
    """Sets up a clean database table for testing."""
    settings = load_settings(TEST_ENV)
    engine = get_postgres_engine(settings)
    
    # Create the 'raw' schema and the table
    Base.metadata.create_all(engine)
    
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    yield session
    
    # Teardown: Drop the table after the test
    session.close()
    Base.metadata.drop_all(engine)

def test_etl_pipeline_end_to_end(db_session) -> None:
    """Test fetching live data, transforming it, and loading it into Postgres."""
    settings = load_settings(TEST_ENV)
    
    # 1. Extract
    api_data = fetch_bakun_telemetry(settings)
    
    # 2. Transform & Load
    rows_inserted = transform_and_load_bakun_telemetry(db_session, api_data)
    
    # 3. Verify
    assert rows_inserted > 0, "Pipeline reported 0 rows inserted."
    
    # Query the database to prove the rows exist
    db_count = db_session.query(RawOpenMeteo).count()
    assert db_count == rows_inserted, f"Expected {rows_inserted} rows in DB, found {db_count}."
    
    # Verify the data types were correctly mapped
    sample_row = db_session.query(RawOpenMeteo).first()
    
    # TODO 2: Add assertions to verify that sample_row.timestamp is a datetime object,
    # and that sample_row.temperature_2m is a float (or None, if missing).
    assert sample_row is not None

    assert isinstance(sample_row.timestamp, datetime)
    assert sample_row.temperature_2m is None or isinstance(sample_row.temperature_2m, float)