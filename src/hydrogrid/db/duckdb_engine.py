"""DuckDB in-process OLAP engine with PostgreSQL scanner integration."""

from __future__ import annotations
from typing import Optional
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

    # 1. Initialize an in-memory DuckDB connection
    con: DuckDBPyConnection = duckdb.connect(database=":memory:")

    # 2. Build PostgreSQL connection string
    pg_conn_str = (
        f"dbname={cfg.postgres_db} "
        f"user={cfg.postgres_user} "
        f"password={cfg.postgres_password} "
        f"host={cfg.postgres_host} "
        f"port={cfg.postgres_port}"
    )

    # 3. Install, load postgres extension, and attach catalog
    read_only_flag = "true" if read_only_pg else "false"
    con.execute("INSTALL postgres;")
    con.execute("LOAD postgres;")
    con.execute(
        f"ATTACH '{pg_conn_str}' AS pg_dw (TYPE POSTGRES, READ_ONLY {read_only_flag});"
    )

    return con


def query_duckdb(
    sql_query: str,
    con: Optional[DuckDBPyConnection] = None,
    settings: Optional[Settings] = None,
) -> duckdb.DuckDBPyRelation:
    """Executes an OLAP query against the attached warehouse and returns a DuckDB relation.

    Args:
        sql_query: SQL statement targeting attached schemas.
        con: Optional existing connection; creates a transient connection if None.
        settings: Optional settings instance when spawning a new connection.

    Returns:
        DuckDBPyRelation: Lazy relation object convertible to Arrow, Polars, or Pandas.
    """
    connection = con if con is not None else get_duckdb_connection(settings=settings)
    return connection.sql(sql_query)