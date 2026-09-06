"""Verification tests for DuckDB OLAP engine and Postgres scanner integration."""

from __future__ import annotations
from datetime import datetime, timedelta
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from duckdb import DuckDBPyConnection

from hydrogrid.config import load_settings
from hydrogrid.db.engine import get_postgres_engine
from hydrogrid.db.base import Base
from hydrogrid.db.models import RawOpenMeteo
from hydrogrid.ingest.openmeteo import fetch_bakun_telemetry
from hydrogrid.ingest.pipeline import transform_and_load_bakun_telemetry
from hydrogrid.warehouse.transform import promote_to_warehouse
from hydrogrid.warehouse.analytics import create_analytics_views
from hydrogrid.db.duckdb_engine import get_duckdb_connection, query_duckdb

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
def populated_db():
    """Seeds Postgres with telemetry, promotes to warehouse, and creates analytics views."""
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
        for hour in range(48):
            synthetic_log = RawOpenMeteo(
                timestamp=base_time - timedelta(hours=hour),
                temperature_2m=26.5 + (hour % 4),
                relative_humidity_2m=82.0,
                precipitation=1.2 if hour % 6 == 0 else 0.0,
                global_tilted_irradiance=250.0 if 6 <= (hour % 24) <= 18 else 0.0,
            )
            session.add(synthetic_log)
        session.commit()

    promote_to_warehouse(session)
    create_analytics_views(engine)

    yield settings

    session.close()
    with engine.begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS warehouse.v_telemetry_analytics;"))
    Base.metadata.drop_all(engine)


def test_duckdb_postgres_attachment(populated_db):
    """Verify DuckDB attaches to Postgres and exposes the pg_dw catalog."""
    settings = populated_db
    con: DuckDBPyConnection = get_duckdb_connection(settings=settings)
    assert con is not None

    databases = con.execute("SHOW DATABASES;").fetchall()
    db_names = [row[0] for row in databases]
    assert "pg_dw" in db_names, f"Expected 'pg_dw' in attached databases, got: {db_names}"


def test_duckdb_query_dim_asset(populated_db):
    """Verify DuckDB queries the warehouse.dim_asset table directly."""
    settings = populated_db
    con: DuckDBPyConnection = get_duckdb_connection(settings=settings)

    rel = con.execute(
        "SELECT id, asset_name, asset_type FROM pg_dw.warehouse.dim_asset;"
    ).fetchall()

    assert len(rel) > 0, "Expected records in pg_dw.warehouse.dim_asset"
    asset_names = [row[1] for row in rel]
    assert "Bakun Dam" in asset_names


def test_duckdb_query_analytics_view_to_dataframe(populated_db):
    """Verify DuckDB queries warehouse.v_telemetry_analytics and converts to Pandas DataFrame."""
    settings = populated_db
    query = """
        SELECT 
            asset_name,
            timestamp,
            temperature_2m,
            rolling_24h_temp,
            rolling_24h_precip
        FROM pg_dw.warehouse.v_telemetry_analytics
        ORDER BY timestamp DESC
        LIMIT 10;
    """
    rel = query_duckdb(query, settings=settings)
    df = rel.df()

    assert not df.empty
    assert len(df) <= 10
    assert "rolling_24h_temp" in df.columns
    assert "rolling_24h_precip" in df.columns