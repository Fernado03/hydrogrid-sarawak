"""SQLAlchemy ORM models for the HydroGrid Sarawak Warehouse."""

from sqlalchemy import Column, Integer, Float, DateTime, String, ForeignKey
from sqlalchemy.orm import relationship
from hydrogrid.db.base import Base

class RawOpenMeteo(Base):
    """Raw telemetry table for Bakun Dam and multi-asset Open-Meteo data."""
    
    __tablename__ = "openmeteo_bakun"
    __table_args__ = {"schema": "raw"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_name = Column(String, nullable=False, default="Bakun Dam")
    timestamp = Column(DateTime, nullable=False)
    temperature_2m = Column(Float, nullable=True)
    relative_humidity_2m = Column(Float, nullable=True)
    precipitation = Column(Float, nullable=True)
    global_tilted_irradiance = Column(Float, nullable=True)
class DimAsset(Base):
    """Dimension table for Energy Assets (Dams, Solar Farms, H2 Hubs)."""
    __tablename__ = "dim_asset"
    __table_args__ = {"schema": "warehouse"}

    id = Column(Integer, primary_key=True)
    asset_name = Column(String, nullable=False, unique=True)
    asset_type = Column(String, nullable=False) # e.g., 'Hydro', 'Solar'
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    capacity_mw = Column(Float, nullable=True)
    # Relationship to facts (optional but good for ORM)
    telemetry_facts = relationship("FactTelemetry", back_populates="asset")


class FactTelemetry(Base):
    """Fact table for hourly telemetry readings."""
    __tablename__ = "fact_telemetry"
    __table_args__ = {"schema": "warehouse"}

    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("warehouse.dim_asset.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    
    # Metrics
    temperature_2m = Column(Float)
    relative_humidity_2m = Column(Float)
    precipitation = Column(Float)
    global_tilted_irradiance = Column(Float) # Critical for Solar
    created_at = Column(DateTime, nullable=True)

    # Relationship back to dimension
    asset = relationship("DimAsset", back_populates="telemetry_facts")