"""ETL Pipeline for transforming and loading Open-Meteo telemetry."""

from sqlalchemy.orm import Session
from hydrogrid.ingest.models import OpenMeteoResponse
from hydrogrid.db.models import RawOpenMeteo
from hydrogrid.db.base import Base

from hydrogrid.warehouse.transform import promote_to_warehouse

__all__ = [
    "ensure_raw_table",
    "transform_and_load_telemetry",
    "transform_and_load_bakun_telemetry",
    "promote_to_warehouse",
]


def ensure_raw_table(session: Session) -> None:
    """Idempotently creates the raw telemetry table if it does not exist."""
    Base.metadata.create_all(session.get_bind())


def transform_and_load_telemetry(
    session: Session,
    api_data: dict,
    asset_name: str = "Bakun Dam",
) -> int:
    """Validates, transposes, and bulk-inserts Open-Meteo data into Postgres for an asset.

    Args:
        session: Active SQLAlchemy Session.
        api_data: The JSON dictionary returned by fetch_telemetry / fetch_bakun_telemetry.
        asset_name: Name of the asset (default: "Bakun Dam").

    Returns:
        int: The number of rows inserted.
    """
    ensure_raw_table(session)
    validated_data = OpenMeteoResponse(**api_data)
    hourly = validated_data.hourly
    
    rows_to_insert = [
        RawOpenMeteo(
            asset_name=asset_name,
            timestamp=ts,
            temperature_2m=temp,
            relative_humidity_2m=humidity,
            precipitation=precip,
            global_tilted_irradiance=irradiance,
        )
        for ts, temp, humidity, precip, irradiance in zip(
            hourly.time,
            hourly.temperature_2m,
            hourly.relative_humidity_2m,
            hourly.precipitation,
            hourly.global_tilted_irradiance,
            strict=True,
        )
    ]
    
    session.add_all(rows_to_insert)
    session.commit()

    return len(rows_to_insert)


def transform_and_load_bakun_telemetry(session: Session, api_data: dict) -> int:
    """Validates, transposes, and bulk-inserts Bakun Open-Meteo data into Postgres.

    Backwards-compatible wrapper around transform_and_load_telemetry.
    """
    return transform_and_load_telemetry(session, api_data, asset_name="Bakun Dam")