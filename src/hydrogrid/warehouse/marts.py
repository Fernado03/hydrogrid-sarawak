"""Telemetry data mart aggregations for downstream ML and BI consumption."""

from __future__ import annotations
from sqlalchemy import Engine, text


def create_daily_telemetry_mart(engine: Engine) -> None:
    """Creates and populates the marts.daily_telemetry_summary table.

    Aggregates hourly warehouse.fact_telemetry records to daily granularity
    joined with warehouse.dim_asset metadata.

    Args:
        engine: Active SQLAlchemy connection engine.
    """
    ddl_and_populate_sql = text("""
    CREATE SCHEMA IF NOT EXISTS marts;

    DROP TABLE IF EXISTS marts.daily_telemetry_summary;

    CREATE TABLE marts.daily_telemetry_summary AS
    SELECT 
        d.id AS asset_id,
        d.asset_name,
        d.asset_type,
        DATE(f.timestamp) AS summary_date,
        ROUND(AVG(f.temperature_2m)::numeric, 2) AS avg_temp_c,
        ROUND(SUM(f.precipitation)::numeric, 2) AS total_precip_mm,
        MAX(f.global_tilted_irradiance) AS peak_irradiance_wm2,
        COUNT(*) AS readings_count
    FROM warehouse.fact_telemetry f
    JOIN warehouse.dim_asset d ON f.asset_id = d.id
    GROUP BY d.id, d.asset_name, d.asset_type, DATE(f.timestamp)
    ORDER BY summary_date DESC, d.asset_name ASC;
    """)

    with engine.begin() as conn:
        conn.execute(ddl_and_populate_sql)