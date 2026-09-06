"""Verification tests for Agent Tools: Schema Inspection, Safe SQL, and Policy RAG."""

from __future__ import annotations
from datetime import datetime, timedelta
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from hydrogrid.config import load_settings
from hydrogrid.db.engine import get_postgres_engine
from hydrogrid.db.base import Base
from hydrogrid.db.models import RawOpenMeteo
from hydrogrid.warehouse.transform import promote_to_warehouse
from hydrogrid.warehouse.analytics import create_analytics_views
from hydrogrid.warehouse.marts import create_daily_telemetry_mart
from hydrogrid.agents.tools import (
    execute_safe_sql,
    inspect_warehouse_schema,
    search_sarawak_energy_policy,
)

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


@pytest.fixture(scope="module")
def tools_db():
    """Seeds Postgres with complete warehouse models and views for tool testing."""
    settings = load_settings(TEST_ENV)
    engine = get_postgres_engine(settings)
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    base_time = datetime.utcnow()
    for hour in range(48):
        session.add(
            RawOpenMeteo(
                timestamp=base_time - timedelta(hours=hour),
                temperature_2m=26.0 + (hour % 4),
                relative_humidity_2m=82.0,
                precipitation=5.0 if hour % 8 == 0 else 0.0,
                global_tilted_irradiance=400.0 if 8 <= (hour % 24) <= 16 else 0.0,
            )
        )
    session.commit()

    promote_to_warehouse(session)
    create_analytics_views(engine)
    create_daily_telemetry_mart(engine)

    yield settings

    session.close()
    with engine.begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS warehouse.v_telemetry_analytics;"))
        conn.execute(text("DROP TABLE IF EXISTS marts.daily_telemetry_summary;"))
    Base.metadata.drop_all(engine)


def test_inspect_warehouse_schema(tools_db):
    """Verify tool discovers warehouse tables and views."""
    settings = tools_db
    schema_summary = inspect_warehouse_schema(settings=settings)
    
    assert "dim_asset" in schema_summary
    assert "fact_telemetry" in schema_summary
    assert "v_telemetry_analytics" in schema_summary


def test_execute_safe_sql_valid_select(tools_db):
    """Verify valid read-only SELECT returns formatted data."""
    settings = tools_db
    query = "SELECT asset_name, asset_type FROM pg_dw.warehouse.dim_asset LIMIT 5;"
    result = execute_safe_sql(query, settings=settings)

    assert "Bakun Dam" in result
    assert "Hydro" in result


def test_execute_safe_sql_blocks_mutation(tools_db):
    """Verify tool rejects destructive DDL/DML queries."""
    settings = tools_db

    # Test DROP attempt
    drop_attempt = "DROP TABLE pg_dw.warehouse.dim_asset;"
    res1 = execute_safe_sql(drop_attempt, settings=settings)
    assert "ERROR" in res1

    # Test DELETE attempt
    delete_attempt = "DELETE FROM pg_dw.warehouse.fact_telemetry;"
    res2 = execute_safe_sql(delete_attempt, settings=settings)
    assert "ERROR" in res2

    # Test Semicolon query chaining injection
    chain_attempt = "SELECT 1; DROP TABLE pg_dw.warehouse.dim_asset;"
    res3 = execute_safe_sql(chain_attempt, settings=settings)
    assert "ERROR" in res3


def test_search_sarawak_energy_policy():
    """Verify policy RAG tool returns relevant sections based on domain keywords."""
    # Search Bakun reservoir rules
    bakun_res = search_sarawak_energy_policy("What is the flood safety limit for Bakun reservoir?")
    assert "212m" in bakun_res
    assert "spillway" in bakun_res

    # Search Hydrogen allocation
    h2_res = search_sarawak_energy_policy("How does Bintulu hydrogen hub allocate surplus hydro?")
    assert "Bintulu H2 Hub" in h2_res
    assert "Electrolyzers" in h2_res