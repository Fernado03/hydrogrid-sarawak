"""Operational tools for database inspection, safe SQL execution, and policy RAG."""

from __future__ import annotations
import re
from typing import Any, Dict, List, Optional
import pandas as pd

from hydrogrid.config import Settings, load_settings
from hydrogrid.db.duckdb_engine import get_duckdb_connection, query_duckdb

# In-memory policy knowledge base modeling Sarawak Energy guidelines
SARAWAK_POLICY_KNOWLEDGE_BASE = [
    {
        "topic": "Bakun Dam Reservoir Safety",
        "keywords": ["bakun", "reservoir", "safety", "water level", "flood", "rainfall"],
        "content": (
            "Bakun Hydroelectric Dam Operational Rules: Normal operating reservoir water level is "
            "between 212m and 228m above sea level. Severe rainfall alert is triggered if 24-hour "
            "rolling precipitation exceeds 50.0 mm. Controlled spillway discharge must be initiated "
            "if reservoir level approaches 225m during monsoon periods to prevent downstream flooding."
        ),
    },
    {
        "topic": "Batang Ai Floating Solar & Hydro Balancing",
        "keywords": ["batang ai", "solar", "floating solar", "intermittency", "frequency"],
        "content": (
            "Batang Ai 50MW Floating Solar Hybrid Protocol: Floating solar arrays fluctuate with local "
            "cloud cover. If solar irradiance drops below 150 W/m² between 10:00 and 15:00, Batang Ai "
            "hydro turbines must ramp generation at a rate of 5 MW/min to maintain grid frequency at 50.0 Hz."
        ),
    },
    {
        "topic": "Bintulu Green Hydrogen Hub Quota",
        "keywords": ["bintulu", "hydrogen", "h2", "electrolyzer", "surplus", "dispatch"],
        "content": (
            "Sarawak Hydrogen Economy Transition Framework: Electrolyzers at Bintulu H2 Hub operate "
            "on off-peak surplus hydro power. Minimum allocated base power is 100 MW. When grid demand "
            "peaks (19:00 - 22:00), hydrogen electrolysis must throttle by up to 60% unless total hydro "
            "storage across Bakun and Murum exceeds 85% capacity."
        ),
    },
]


def inspect_warehouse_schema(settings: Optional[Settings] = None) -> str:
    """Inspects the DuckDB catalog to return accessible schemas, tables, and views.

    Returns:
        str: Formatted markdown schema summary for LLM prompt context.
    """
    cfg = settings or load_settings()
    con = get_duckdb_connection(settings=cfg)

    tables = con.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('warehouse', 'marts');").fetchall()
    return "\n".join(f"- `{schema}.{name}`" for schema, name in tables)


def execute_safe_sql(sql_query: str, settings: Optional[Settings] = None) -> str:
    """Executes a strictly read-only SQL query via DuckDB against the attached warehouse."""
    clean_query = sql_query.strip()

    # Semicolon check (preventing query chaining like "SELECT 1; DROP TABLE ...")
    if ";" in clean_query.rstrip(";"):
        return "ERROR: Query chaining with semicolons is strictly prohibited for security."

    if not re.match(r"^(SELECT|WITH)\b", clean_query, re.IGNORECASE):
        return "ERROR: Only read-only SELECT or WITH queries are allowed. Mutation queries are prohibited."

    if re.search(r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE|GRANT|REVOKE)\b", clean_query, re.IGNORECASE):
        return "ERROR: Mutation queries are prohibited. Only read-only SELECT or WITH queries are allowed."

    try:
        rel = query_duckdb(clean_query, settings=settings)
        df = rel.df()
        if df.empty:
            return "Query executed successfully. 0 rows returned."
        try:
            return df.head(50).to_markdown(index=False)
        except ImportError:
            return df.head(50).to_string(index=False)
    except Exception as e:
        return f"ERROR executing SQL: {type(e).__name__} - {str(e)}"

def search_sarawak_energy_policy(query: str) -> str:
    """Retrieves relevant Sarawak Energy transition and dam safety policy excerpts.

    Performs keyword relevance matching against policy guidelines.

    Args:
        query: Operator search phrase or policy question.

    Returns:
        str: Matching policy sections or fallback notice.
    """
    if query:
        query_lower = query.lower()
        matched_sections = []
        for policy in SARAWAK_POLICY_KNOWLEDGE_BASE:
            if any(keyword in query_lower for keyword in policy["keywords"]):
                matched_sections.append(f"**{policy['topic']}**\n{policy['content']}")
        if matched_sections:
            return "\n\n".join(matched_sections)
    return "No specific Sarawak Energy policy found for this query."