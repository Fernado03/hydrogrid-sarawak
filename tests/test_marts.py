"""Verification tests for Daily Telemetry Mart."""

from __future__ import annotations
from datetime import datetime, timedelta
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from hydrogrid.config import load_settings
from hydrogrid.db.engine import get_postgres_engine
from hydrogrid.db.base import Base
from hydrogrid.db.models import RawOpenMeteo
from hydrogrid.ingest.openmeteo import fetch_bakun_telemetry
from hydrogrid.ingest.pipeline import transform_and_load_bakun_telemetry
from hydrogrid.warehouse.transform import promote_to_warehouse
from hydrogrid.warehouse.marts import create_daily_telemetry_mart
from hydrogrid.db.duckdb_engine import query_duckdb

TEST_ENV = {
    "HYDROGRID_ENV": "test",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "hydrogrid_warehouse",
    "POSTGRES_USER": "hydrogrid",
    "POSTGRES_PASSWORD": "change_me",
    "OPEN_METEO_BASE_URL": "https://api.open-meteo.com",
    "LLM_BASE_URL": "https://llm.example.com/v1",
    "LLM_API_KEY": "test-key",
}


@pytest.fixture(scope="function")
def seeded_warehouse():
    """Populates warehouse and yields settings."""
    settings = load_settings(TEST_ENV)
    engine = get_postgres_engine(settings)
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        api_data = fetch_bakun_telemetry(settings)
        transform_and_load_bakun_telemetry(session, api_data)
    except Exception:
        base_time = datetime.utcnow()
        for hour in range(72):
            session.add(
                RawOpenMeteo(
                    timestamp=base_time - timedelta(hours=hour),
                    temperature_2m=27.0 + (hour % 5),
                    relative_humidity_2m=80.0,
                    precipitation=2.5 if hour % 12 == 0 else 0.0,
                    global_tilted_irradiance=450.0 if 8 <= (hour % 24) <= 16 else 0.0,
                )
            )
        session.commit()

    promote_to_warehouse(session)
    session.close()

    yield settings, engine

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS marts.daily_telemetry_summary;"))
    Base.metadata.drop_all(engine)


def test_create_daily_telemetry_mart(seeded_warehouse):
    """Verify marts.daily_telemetry_summary creation and aggregations in Postgres."""
    settings, engine = seeded_warehouse

    create_daily_telemetry_mart(engine)

    query = text("SELECT * FROM marts.daily_telemetry_summary;")
    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()

    assert len(rows) > 0, "marts.daily_telemetry_summary should have records."
    
    first_row = rows[0]._mapping
    assert "summary_date" in first_row
    assert "avg_temp_c" in first_row
    assert "total_precip_mm" in first_row
    assert "peak_irradiance_wm2" in first_row
    assert "readings_count" in first_row
    assert first_row["readings_count"] > 0


def test_duckdb_query_marts(seeded_warehouse):
    """Verify DuckDB can read directly from marts.daily_telemetry_summary."""
    settings, engine = seeded_warehouse
    create_daily_telemetry_mart(engine)

    query = """
        SELECT 
            asset_name,
            summary_date,
            avg_temp_c,
            total_precip_mm
        FROM pg_dw.marts.daily_telemetry_summary
        ORDER BY summary_date DESC;
    """
    rel = query_duckdb(query, settings=settings)
    df = rel.df()

    assert not df.empty
    assert "avg_temp_c" in df.columns
    assert "total_precip_mm" in df.columns