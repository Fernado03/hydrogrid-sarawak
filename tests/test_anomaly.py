"""Verification tests for Telemetry Anomaly Detection pipeline."""

from __future__ import annotations
from datetime import datetime, timedelta
import os
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
import mlflow

from hydrogrid.config import load_settings
from hydrogrid.db.engine import get_postgres_engine
from hydrogrid.db.base import Base
from hydrogrid.db.models import RawOpenMeteo
from hydrogrid.warehouse.transform import promote_to_warehouse
from hydrogrid.warehouse.analytics import create_analytics_views
from hydrogrid.ml.anomaly import load_raw_telemetry_for_asset, train_anomaly_detector

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
def anomaly_db():
    """Seeds Postgres with regular readings plus one injected catastrophic anomaly."""
    settings = load_settings(TEST_ENV)
    engine = get_postgres_engine(settings)
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    base_time = datetime.utcnow()
    # 1. Seed 60 normal records (temperature around 25-30C, normal rain)
    for hour in range(60):
        session.add(
            RawOpenMeteo(
                timestamp=base_time - timedelta(hours=hour),
                temperature_2m=26.0 + (hour % 4),
                relative_humidity_2m=82.0,
                precipitation=1.0 if hour % 6 == 0 else 0.0,
                global_tilted_irradiance=300.0 if 7 <= (hour % 24) <= 17 else 0.0,
            )
        )

    # 2. Inject one extreme outlier reading (sensor lightning strike glitch)
    session.add(
        RawOpenMeteo(
            timestamp=base_time - timedelta(hours=61),
            temperature_2m=98.5,  # Extreme heat outlier
            relative_humidity_2m=5.0,  # Impossible dryness
            precipitation=280.0,  # Extreme flash flood anomaly
            global_tilted_irradiance=1500.0,
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


def test_anomaly_detection_pipeline(anomaly_db):
    """Verify Isolation Forest catches injected outliers and logs to MLflow."""
    settings = anomaly_db

    df = load_raw_telemetry_for_asset(asset_name="Bakun Dam", settings=settings)
    assert not df.empty
    assert len(df) == 61

    # Train anomaly detector with 5% contamination
    model, df_scored, metadata = train_anomaly_detector(
        df=df,
        contamination=0.05,
        experiment_name="test_anomaly_experiments",
    )

    # Assert enriched columns exist
    assert "anomaly_score" in df_scored.columns
    assert "is_anomaly" in df_scored.columns
    assert metadata["anomaly_count"] > 0

    # Verify the injected extreme anomaly was flagged
    outlier_row = df_scored[df_scored["temperature_2m"] > 90.0]
    assert not outlier_row.empty
    assert outlier_row["is_anomaly"].iloc[0] == True

    # Verify MLflow tracking
    client = mlflow.tracking.MlflowClient()
    run = client.get_run(metadata["run_id"])
    assert run.info.status == "FINISHED"
    assert "anomaly_count" in run.data.metrics
    assert run.data.metrics["anomaly_count"] >= 1.0