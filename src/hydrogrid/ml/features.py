"""Feature engineering pipeline for HydroGrid ML forecasting models."""

from __future__ import annotations
from typing import Optional
import numpy as np
import pandas as pd

from hydrogrid.config import Settings, load_settings
from hydrogrid.db.duckdb_engine import query_duckdb


def extract_telemetry_features(
    asset_name: str = "Bakun Dam",
    settings: Optional[Settings] = None,
) -> pd.DataFrame:
    """Extracts telemetry from DuckDB and engineers ML-ready features.

    Features generated:
    - hour_sin, hour_cos: Cyclical time encodings.
    - precipitation_lag_1h, precipitation_lag_24h: Hydrological rainfall delay.
    - temp_lag_1h: Thermal inertia lag.

    Args:
        asset_name: Target asset in dim_asset.
        settings: Application settings configuration.

    Returns:
        pd.DataFrame: Cleaned feature matrix indexed chronologically without NaNs.
    """
    cfg = settings or load_settings()

    # 1. Query analytical telemetry via DuckDB
    sql_query = f"""
        SELECT 
            timestamp,
            temperature_2m,
            precipitation,
            global_tilted_irradiance
        FROM pg_dw.warehouse.v_telemetry_analytics
        WHERE asset_name = '{asset_name}'
        ORDER BY timestamp ASC;
    """

    rel = query_duckdb(sql_query, settings=cfg)
    df = rel.df()

    if df.empty:
        return df

    # Ensure timestamp is datetime and sort
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    # 2. Cyclical Hour Encoding
    df["hour_sin"] = np.sin(2.0 * np.pi * df["timestamp"].dt.hour / 24.0)
    df["hour_cos"] = np.cos(2.0 * np.pi * df["timestamp"].dt.hour / 24.0)

    # 3. Autoregressive Lags
    df["precipitation_lag_1h"] = df["precipitation"].shift(1)
    df["precipitation_lag_24h"] = df["precipitation"].shift(24)
    df["temp_lag_1h"] = df["temperature_2m"].shift(1)

    # 4. Clean boundaries
    clean_df = df.dropna().reset_index(drop=True)

    return clean_df