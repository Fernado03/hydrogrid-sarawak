"""Automated setup for HydroGrid Sarawak warehouse schemas."""

import logging
from sqlalchemy import text, inspect
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# The assembly line schemas for our data warehouse
SCHEMAS_TO_CREATE = ["raw", "staging", "warehouse", "marts"]

def setup_schemas(engine: Engine) -> None:
    """Creates the core warehouse schemas if they do not already exist.
    
    Args:
        engine: A connected SQLAlchemy Engine.
    """
    inspector = inspect(engine)
    existing_schemas = inspector.get_schema_names()
    
    with engine.connect() as conn:
        for schema in SCHEMAS_TO_CREATE:
            if schema not in existing_schemas:
                conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
                logger.info("Created schema: %s", schema)

        conn.commit()