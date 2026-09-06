"""Verification tests for ML Feature Engineering pipeline."""

from __future__ import annotations
from datetime import datetime, timedelta
import pytest
import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from hydrogrid.config import load_settings
from hydrogrid.db.engine import get_postgres_engine
from hydrogrid.db.base import Base
from hydrogrid.db.models import RawOpenMeteo
from hydrogrid.ingest.openmeteo import fetch_bakun_telemetry
from hydrogrid.ingest.pipeline import transform_and_load_bakun_telemetry
from hydrogrid.warehouse.transform import promote_to_warehouse
from hydrogrid.warehouse.analytics import create_analytics_views
from hydrogrid.ml.features import extract_telemetry_features

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
def feature_db():
    """Seeds Postgres with enough chronological hourly logs to support 24h lags."""
    settings = load_settings(TEST_ENV)
    engine = get_postgres_engine(settings)
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Seed at least 72 hours of telemetry to validate 24-hour lag structures
    try:
        api_data = fetch_bakun_telemetry(settings)
        transform_and_load_bakun_telemetry(session, api_data)
    except Exception:
        base_time = datetime.utcnow()
        for hour in range(96):
            session.add(
                RawOpenMeteo(
                    timestamp=base_time - timedelta(hours=hour),
                    temperature_2m=25.0 + (hour % 6),
                    relative_humidity_2m=80.0,
                    precipitation=3.0 if hour % 12 == 0 else 0.0,
                    global_tilted_irradiance=500.0 if 7 <= (hour % 24) <= 17 else 0.0,
                )
            )
        session.commit()

    promote_to_warehouse(session)
    create_analytics_views(engine)

    yield settings

    session.close()
    with engine.begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS warehouse.v_telemetry_analytics;"))
    Base.metadata.drop_all(engine)


def test_extract_telemetry_features(feature_db):
    """Verify feature dataframe structure, lag columns, and mathematical boundaries."""
    settings = feature_db
    df = extract_telemetry_features(asset_name="Bakun Dam", settings=settings)

    assert not df.empty, "Feature extraction returned empty DataFrame."
    
    # Verify expected columns
    expected_cols = [
        "timestamp",
        "temperature_2m",
        "precipitation",
        "global_tilted_irradiance",
        "hour_sin",
        "hour_cos",
        "precipitation_lag_1h",
        "precipitation_lag_24h",
        "temp_lag_1h",
    ]
    for col in expected_cols:
        assert col in df.columns, f"Missing feature column: {col}"

    # Verify cyclical encodings stay strictly within [-1.0, 1.0]
    assert df["hour_sin"].between(-1.0, 1.0).all()
    assert df["hour_cos"].between(-1.0, 1.0).all()

    # Verify no NaN values remain in the prepared training set
    assert df.isna().sum().sum() == 0, "Feature dataframe contains lingering NaNs."