"""Telemetry anomaly detection pipeline using Isolation Forest and MLflow."""

from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
import os
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from hydrogrid.config import Settings, load_settings
from hydrogrid.db.duckdb_engine import query_duckdb


ANOMALY_FEATURE_COLUMNS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "global_tilted_irradiance",
]


def load_raw_telemetry_for_asset(
    asset_name: str = "Bakun Dam",
    settings: Optional[Settings] = None,
) -> pd.DataFrame:
    """Queries telemetry directly from the analytics view using DuckDB."""
    cfg = settings or load_settings()
    sql_query = f"""
        SELECT 
            timestamp,
            temperature_2m,
            relative_humidity_2m,
            precipitation,
            global_tilted_irradiance
        FROM pg_dw.warehouse.v_telemetry_analytics
        WHERE asset_name = '{asset_name}'
        ORDER BY timestamp ASC;
    """
    rel = query_duckdb(sql_query, settings=cfg)
    df = rel.df()
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def train_anomaly_detector(
    df: pd.DataFrame,
    contamination: float = 0.05,
    random_state: int = 42,
    experiment_name: str = "hydrogrid_anomaly_detection",
) -> Tuple[IsolationForest, pd.DataFrame, Dict[str, Any]]:
    """Trains an Isolation Forest on telemetry and logs parameters to MLflow.

    Args:
        df: Telemetry DataFrame containing ANOMALY_FEATURE_COLUMNS.
        contamination: Expected proportion of outliers in the data.
        random_state: Random seed for reproducibility.
        experiment_name: MLflow experiment namespace.

    Returns:
        Tuple containing:
        - Trained IsolationForest model
        - DataFrame enriched with 'anomaly_score' and 'is_anomaly' (-1 for outlier, 1 for normal)
        - Metadata dictionary containing run_id and detected anomaly counts
    """
    if df.empty or len(df) < 20:
        raise ValueError(f"Insufficient records ({len(df)}) for anomaly training.")

    X = df[ANOMALY_FEATURE_COLUMNS].copy()

    # 1. Setup MLflow SQLite backend
    os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"
    db_path = os.path.abspath("mlflow.db").replace("\\", "/")
    mlflow.set_tracking_uri(f"sqlite:///{db_path}")
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run(run_name="isolation_forest_telemetry") as run:
        iso_forest = IsolationForest(
            contamination=contamination,
            random_state=random_state,
            n_estimators=100,
        )

        iso_forest.fit(X)

        labels = iso_forest.predict(X)
        scores = iso_forest.decision_function(X)

        # Enrich DataFrame with results
        df_scored = df.copy()
        df_scored["anomaly_score"] = scores
        df_scored["is_anomaly"] = labels == -1  # Boolean flag: True if anomaly

        anomaly_count = int(df_scored["is_anomaly"].sum())

        mlflow.log_param("contamination", contamination)
        mlflow.log_param("n_estimators", 100)
        mlflow.log_metric("total_records", len(df_scored))
        mlflow.log_metric("anomaly_count", anomaly_count)
        mlflow.sklearn.log_model(iso_forest, artifact_path="model")
        

        metadata = {
            "run_id": run.info.run_id,
            "total_records": len(df_scored),
            "anomaly_count": anomaly_count,
            "contamination": contamination,
        }

        return iso_forest, df_scored, metadata