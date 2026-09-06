"""Verification tests for LightGBM training pipeline and MLflow tracking."""

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
from hydrogrid.ingest.openmeteo import fetch_bakun_telemetry
from hydrogrid.ingest.pipeline import transform_and_load_bakun_telemetry
from hydrogrid.warehouse.transform import promote_to_warehouse
from hydrogrid.warehouse.analytics import create_analytics_views
from hydrogrid.ml.train import train_inflow_forecaster

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
def training_db():
    """Seeds warehouse with a 120-hour telemetry set for machine learning verification."""
    settings = load_settings(TEST_ENV)
    engine = get_postgres_engine(settings)
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    base_time = datetime.utcnow()
    for hour in range(120):
        session.add(
            RawOpenMeteo(
                timestamp=base_time - timedelta(hours=hour),
                temperature_2m=24.0 + (hour % 7),
                relative_humidity_2m=85.0,
                precipitation=4.0 if hour % 12 == 0 else 0.5,
                global_tilted_irradiance=600.0 if 8 <= (hour % 24) <= 16 else 0.0,
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


def test_train_inflow_forecaster(training_db):
    """Verify forecaster training run executes and registers artifacts in MLflow."""
    settings = training_db

    results = train_inflow_forecaster(
        asset_name="Bakun Dam",
        n_estimators=30,
        learning_rate=0.1,
        settings=settings,
        experiment_name="test_hydrogrid_experiments",
    )

    # 1. Assert training return structure
    assert "run_id" in results
    assert "rmse" in results
    assert "mae" in results
    assert "r2" in results
    assert results["rmse"] >= 0.0

    # 2. Verify MLflow logged the run correctly
    client = mlflow.tracking.MlflowClient()
    run = client.get_run(results["run_id"])

    assert run.info.status == "FINISHED"
    assert "rmse" in run.data.metrics
    assert "n_estimators" in run.data.params
    assert run.data.params["n_estimators"] == "30"