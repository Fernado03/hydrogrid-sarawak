"""Verification tests for the Warehouse Star-Schema transformation."""

from __future__ import annotations
import pytest
from sqlalchemy.orm import sessionmaker

from hydrogrid.config import load_settings
from hydrogrid.db.engine import get_postgres_engine
from hydrogrid.db.base import Base
from hydrogrid.db.models import RawOpenMeteo, DimAsset, FactTelemetry
from hydrogrid.ingest.openmeteo import fetch_bakun_telemetry
from hydrogrid.ingest.pipeline import transform_and_load_bakun_telemetry
from hydrogrid.warehouse.transform import promote_to_warehouse

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
    settings = load_settings(TEST_ENV)
    engine = get_postgres_engine(settings)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(engine)

def test_star_schema_transformation(db_session) -> None:
    """Test promoting data from raw to warehouse star-schema."""
    settings = load_settings(TEST_ENV)
    
    # 1. Load Raw Data (We reuse our Task 1.2 logic)
    api_data = fetch_bakun_telemetry(settings)
    raw_count = transform_and_load_bakun_telemetry(db_session, api_data)
    
    # 2. Transform to Warehouse
    # TODO 2: Call promote_to_warehouse(db_session) and capture the return value (fact_count).
    fact_count = promote_to_warehouse(db_session)
    assert fact_count == raw_count, "Fact count should match raw count!"
    
    # 3. Verify the Star-Schema
    assert fact_count > 0, "No facts created."
    
    # Verify the Dimension was created
    bakun = db_session.query(DimAsset).filter_by(asset_name="Bakun Dam").first()
    assert bakun is not None, "Bakun Dam dimension missing."
    assert bakun.asset_type == "Hydro", "Incorrect asset type."
    
    # Verify the Facts are linked correctly
    facts = db_session.query(FactTelemetry).filter_by(asset_id=bakun.id).all()
    assert len(facts) == fact_count, "Fact count mismatch."
    
    # Verify we didn't duplicate raw data (optional but good)
    assert db_session.query(FactTelemetry).count() == raw_count