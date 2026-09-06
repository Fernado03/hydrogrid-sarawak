"""Analytical SQL Views with rolling window aggregations."""

from __future__ import annotations
from sqlalchemy import Engine, text


def create_analytics_views(engine: Engine) -> None:
    """Creates or replaces the warehouse.v_telemetry_analytics view.

    Includes atomic metrics, dimensional metadata, and 24-hour rolling averages.
    """
    sql = """
    CREATE OR REPLACE VIEW warehouse.v_telemetry_analytics AS
    SELECT 
        f.id,
        f.timestamp,
        d.asset_name,
        d.asset_type,
        f.temperature_2m,
        f.relative_humidity_2m,
        f.precipitation,
        f.global_tilted_irradiance,
        AVG(f.temperature_2m) OVER (
            PARTITION BY f.asset_id 
            ORDER BY f.timestamp 
            ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
        ) AS rolling_24h_temp,
        SUM(f.precipitation) OVER (
            PARTITION BY f.asset_id 
            ORDER BY f.timestamp 
            ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
        ) AS rolling_24h_precip
    FROM warehouse.fact_telemetry f
    JOIN warehouse.dim_asset d ON f.asset_id = d.id;
    """
    with engine.begin() as conn:
        conn.execute(text(sql))