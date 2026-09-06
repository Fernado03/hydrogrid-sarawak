"""Database engine management for HydroGrid Sarawak."""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from hydrogrid.config import Settings

def get_postgres_engine(settings: Settings, echo: bool = False) -> Engine:
    """Create a SQLAlchemy engine for the PostgreSQL operational warehouse.
    
    Args:
        settings: Validated application settings.
        echo: If True, SQLAlchemy will log all SQL statements to the console.
        
    Returns:
        A configured SQLAlchemy Engine.
    """
    database_url = (
        f"postgresql+psycopg2://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )
    
    return create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
    )