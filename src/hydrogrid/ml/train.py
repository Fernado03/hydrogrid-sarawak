"""Model training and MLflow tracking pipeline for HydroGrid forecasters."""

from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
import os
import mlflow
import mlflow.lightgbm
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from hydrogrid.config import Settings, load_settings
from hydrogrid.ml.features import extract_telemetry_features


FEATURE_COLUMNS = [
    "hour_sin",
    "hour_cos",
    "temperature_2m",
    "precipitation_lag_1h",
    "precipitation_lag_24h",
    "temp_lag_1h",
]


def prepare_training_data(
    df: pd.DataFrame, 
    test_ratio: float = 0.2
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Prepares feature matrix and target, performing chronological split without shuffle.

    Constructs a hydrological inflow proxy target (m³/s) derived from catchment precipitation:
    target = 50.0 + (18.5 * precipitation_lag_24h) + (4.2 * precipitation_lag_1h)
    """
    target = 50.0 + (18.5 * df["precipitation_lag_24h"]) + (4.2 * df["precipitation_lag_1h"])

    X = df[FEATURE_COLUMNS]
    y = target

    split_idx = int(len(X) * (1 - test_ratio))
    X_train = X.iloc[:split_idx]
    X_test = X.iloc[split_idx:]
    y_train = y.iloc[:split_idx]
    y_test = y.iloc[split_idx:]

    return X_train, X_test, y_train, y_test


def train_inflow_forecaster(
    asset_name: str = "Bakun Dam",
    n_estimators: int = 50,
    learning_rate: float = 0.05,
    max_depth: int = 5,
    settings: Optional[Settings] = None,
    experiment_name: str = "hydrogrid_generation_forecasting",
) -> Dict[str, Any]:
    """Trains a LightGBM regressor and logs run metadata to local MLflow tracking server.

    Args:
        asset_name: Target asset for training.
        n_estimators: Number of boosting trees.
        learning_rate: Boosting learning rate.
        max_depth: Maximum tree depth.
        settings: Application settings configuration.
        experiment_name: MLflow experiment namespace.

    Returns:
        Dict[str, Any]: Run metrics and MLflow run metadata.
    """
    cfg = settings or load_settings()

    # 1. Fetch feature dataset
    df = extract_telemetry_features(asset_name=asset_name, settings=cfg)
    if df.empty or len(df) < 30:
        raise ValueError(f"Insufficient telemetry records ({len(df)}) for model training.")

    X_train, X_test, y_train, y_test = prepare_training_data(df)

    # 2. Configure MLflow tracking (SQLite database backend)
    os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"
    db_path = os.path.abspath("mlflow.db").replace("\\", "/")
    mlflow.set_tracking_uri(f"sqlite:///{db_path}")
    mlflow.set_experiment(experiment_name)

    # 3. MLflow Tracking Context
    with mlflow.start_run(run_name=f"{asset_name}_inflow_lgbm") as run:
        model = LGBMRegressor(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            max_depth=max_depth,
            random_state=42,
        )

        model.fit(X_train, y_train)

        preds = model.predict(X_test)

        rmse = np.sqrt(mean_squared_error(y_test, preds))
        mae = mean_absolute_error(y_test, preds)
        r2 = r2_score(y_test, preds)

        mlflow.log_params({
            "n_estimators": n_estimators,
            "learning_rate": learning_rate,
            "max_depth": max_depth,
        })
        mlflow.log_metrics({
            "rmse": float(rmse),
            "mae": float(mae),
            "r2": float(r2),
        })
        mlflow.lightgbm.log_model(model, artifact_path="model")

        return {
            "run_id": run.info.run_id,
            "rmse": float(rmse),
            "mae": float(mae),
            "r2": float(r2),
            "model": model,
        }