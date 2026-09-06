import os
import json
import urllib.request
from fastapi import APIRouter
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Add this endpoint to app.py
@app.post("/ingest/run")
def trigger_telemetry_ingestion():
    """Fetches 7-day Open-Meteo telemetry for all 4 assets, upserts to warehouse, and refreshes summary marts."""
    user = os.getenv("POSTGRES_USER", "hydrogrid")
    password = os.getenv("POSTGRES_PASSWORD", "change_me")
    host = os.getenv("POSTGRES_HOST", "db")
    port = os.getenv("POSTGRES_PORT", "5432")
    dbname = os.getenv("POSTGRES_DB", "hydrogrid_warehouse")

    engine = create_engine(f"postgresql://{user}:{password}@{host}:{port}/{dbname}")

    assets = [
        ("Bakun Dam", 2.75, 114.05),
        ("Murum Dam", 2.65, 114.30),
        ("Batang Ai", 1.15, 111.90),
        ("Bintulu H2 Hub", 3.20, 113.05),
    ]

    total_upserted = 0

    with Session(engine) as session:
        for name, lat, lon in assets:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,relative_humidity_2m,precipitation,global_tilted_irradiance&forecast_days=7"
            req = urllib.request.Request(url, headers={"User-Agent": "HydroGrid/1.0"})
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])
            hums = hourly.get("relative_humidity_2m", [])
            precips = hourly.get("precipitation", [])
            gtis = hourly.get("global_tilted_irradiance", [])

            res = session.execute(
                text("SELECT id FROM warehouse.dim_asset WHERE asset_name = :name"),
                {"name": name},
            ).fetchone()
            if not res:
                continue
            asset_id = res[0]

            insert_sql = text("""
                INSERT INTO warehouse.fact_telemetry (
                    asset_id, timestamp, temperature_2m, relative_humidity_2m, precipitation, global_tilted_irradiance
                ) VALUES (
                    :asset_id, :ts, :temp, :hum, :precip, :gti
                )
                ON CONFLICT (asset_id, timestamp) DO UPDATE SET
                    temperature_2m = EXCLUDED.temperature_2m,
                    relative_humidity_2m = EXCLUDED.relative_humidity_2m,
                    precipitation = EXCLUDED.precipitation,
                    global_tilted_irradiance = EXCLUDED.global_tilted_irradiance;
            """)

            records = [
                {
                    "asset_id": asset_id,
                    "ts": times[i],
                    "temp": temps[i],
                    "hum": hums[i],
                    "precip": precips[i],
                    "gti": gtis[i],
                }
                for i in range(len(times))
            ]
            session.execute(insert_sql, records)
            total_upserted += len(records)
            session.commit()

        # Materialize analytical mart
        session.execute(text("TRUNCATE TABLE marts.daily_telemetry_summary;"))
        session.execute(text("""
            INSERT INTO marts.daily_telemetry_summary (asset_id, summary_date, avg_temp, total_precip, max_irradiance)
            SELECT 
                asset_id,
                DATE(timestamp) AS summary_date,
                ROUND(AVG(temperature_2m)::numeric, 2),
                ROUND(SUM(precipitation)::numeric, 2),
                ROUND(MAX(global_tilted_irradiance)::numeric, 2)
            FROM warehouse.fact_telemetry
            GROUP BY asset_id, DATE(timestamp);
        """))
        session.commit()

    return {
        "status": "SUCCESS",
        "assets_processed": len(assets),
        "total_records_upserted": total_upserted,
        "mart_refreshed": True,
    }