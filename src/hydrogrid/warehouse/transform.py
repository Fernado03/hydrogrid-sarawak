"""Transformation logic to move data from Raw to Warehouse Star-Schema."""

from sqlalchemy.orm import Session
from hydrogrid.db.models import RawOpenMeteo, DimAsset, FactTelemetry

def promote_to_warehouse(
    session: Session,
    asset_name: str = "Bakun Dam",
    asset_type: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    capacity_mw: float | None = None,
) -> int:
    """Transforms raw telemetry into the warehouse star-schema for a specified asset.
    
    1. Finds or creates the Asset Dimension.
    2. Reads raw rows for the specified asset (or all rows if asset_name is None).
    3. Creates Fact rows linked to the Asset.
    
    Returns:
        int: Number of fact rows inserted.
    """
    # 1. Query raw records filtered by asset_name if column exists
    query = session.query(RawOpenMeteo)
    if hasattr(RawOpenMeteo, "asset_name") and asset_name:
        query = query.filter(
            (RawOpenMeteo.asset_name == asset_name) | (RawOpenMeteo.asset_name.is_(None))
        )
    raw_records = query.all()
    if not raw_records:
        return 0  # No raw data to promote
    
    # 2. Find or create Asset Dimension
    asset = session.query(DimAsset).filter_by(asset_name=asset_name).first()
    if asset is None:
        default_type = "Hydro" if "Dam" in asset_name else ("Industrial" if "Hub" in asset_name else "Other")
        asset = DimAsset(
            asset_name=asset_name,
            asset_type=asset_type or default_type,
            latitude=latitude if latitude is not None else 3.0,
            longitude=longitude if longitude is not None else 113.0,
            capacity_mw=capacity_mw,
        )
        session.add(asset)
        session.flush()

    # 3. Create FactTelemetry instances linked to this asset
    facts = [
        FactTelemetry(
            asset_id=asset.id,
            timestamp=raw.timestamp,
            temperature_2m=raw.temperature_2m,
            relative_humidity_2m=raw.relative_humidity_2m,
            precipitation=raw.precipitation,
            global_tilted_irradiance=raw.global_tilted_irradiance,
        )
        for raw in raw_records
    ]
    
    session.add_all(facts)
    session.commit()

    return len(facts)