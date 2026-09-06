"""DuckDB in-process OLAP engine with PostgreSQL scanner integration."""

from __future__ import annotations
from typing import Any, Optional
import duckdb
from duckdb import DuckDBPyConnection

from hydrogrid.config import Settings, load_settings


def get_duckdb_connection(
    settings: Optional[Settings] = None,
    read_only_pg: bool = True,
) -> DuckDBPyConnection:
    """Instantiates an in-process DuckDB session attached to the PostgreSQL warehouse.

    Args:
        settings: Application settings containing Postgres credentials.
        read_only_pg: Enforce read-only access to the attached Postgres schema.

    Returns:
        DuckDBPyConnection: Configured DuckDB connection with attached Postgres database.
    """
    cfg = settings or load_settings()

    # 1. Initialize an in-memory DuckDB session
    con: DuckDBPyConnection = duckdb.connect(database=":memory:")

    # 2. Build PostgreSQL connection string for DuckDB's ATTACH command.
    # Format options supported by DuckDB postgres extension:
    # "dbname=... user=... password=... host=... port=..."
    # or URI format: "postgresql://user:password@host:port/dbname"
    #
    # TODO 1: Construct pg_conn_str dynamically from cfg attributes
    pg_conn_str = ...

    # 3. Install and load the Postgres extension, then attach the database as 'pg_dw'
    # Required SQL steps in DuckDB:
    #   - INSTALL postgres;
    #   - LOAD postgres;
    #   - ATTACH '<pg_conn_str>' AS pg_dw (TYPE POSTGRES, READ_ONLY <true/false>);
    #
    # TODO 2: Execute INSTALL, LOAD, and ATTACH statements on con
    ...

    return con


def query_duckdb(
    sql_query: str, 
    con: Optional[DuckDBPyConnection] = None,
    settings: Optional[Settings] = None,
) -> duckdb.DuckDBPyRelation:
    """Executes an OLAP query against the attached warehouse and returns a DuckDB relation.

    Args:
        sql_query: SQL statement targeting attached schemas (e.g., 'pg_dw.warehouse.dim_asset').
        con: Optional existing connection; creates a new attached connection if None.
        settings: Optional Settings instance if a new connection must be spawned.

    Returns:
        DuckDBPyRelation: Lazy relation object convertible to Arrow, Polars, or Pandas.
    """
    # TODO 3: Acquire or reuse connection, execute sql_query, and return the relation
    ...