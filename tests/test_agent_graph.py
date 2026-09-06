"""Verification tests for LangGraph state machine, self-correction cycle, and routing."""

from __future__ import annotations
import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import sessionmaker

from hydrogrid.agents.graph import (
    build_agent_graph,
    route_after_planner,
    route_after_sql,
    sql_execution_node,
)
from hydrogrid.agents.state import HydroGridAgentState
from hydrogrid.config import load_settings
from hydrogrid.db.base import Base
from hydrogrid.db.engine import get_postgres_engine
from hydrogrid.db.models import DimAsset


@pytest.fixture(scope="module", autouse=True)
def setup_graph_db():
    """Ensures database schema and dim_asset exist for SQL execution tests."""
    settings = load_settings()
    engine = get_postgres_engine(settings)
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    if not session.query(DimAsset).filter_by(asset_name="Bakun Dam").first():
        session.add(
            DimAsset(
                asset_name="Bakun Dam",
                asset_type="Hydro",
                latitude=2.75,
                longitude=114.05,
            )
        )
        session.commit()
    session.close()

    yield

    Base.metadata.drop_all(engine)


def test_agent_graph_compilation():
    """Verify LangGraph compiles with expected node topology."""
    app = build_agent_graph()
    assert isinstance(app, CompiledStateGraph)

    nodes = app.nodes.keys()
    assert "planner" in nodes
    assert "execute_sql" in nodes
    assert "retrieve_policy" in nodes
    assert "synthesizer" in nodes


def test_route_after_planner():
    """Verify planner router directs to SQL execution, policy, or synthesizer."""
    # 1. Routes to SQL execution when SQL is authored
    state_sql: HydroGridAgentState = {
        "messages": [HumanMessage(content="What is Bakun's average temp?")],
        "generated_sql": "SELECT AVG(temperature_2m) FROM pg_dw.warehouse.fact_telemetry;",
        "sql_query_result": None,
        "policy_context": None,
        "iteration_count": 1,
        "error_message": None,
    }
    assert route_after_planner(state_sql) == "execute_sql"

    # 2. Routes to policy retrieval when question asks for rules
    state_policy: HydroGridAgentState = {
        "messages": [HumanMessage(content="What are the Bakun reservoir flood safety limits?")],
        "generated_sql": None,
        "sql_query_result": None,
        "policy_context": None,
        "iteration_count": 1,
        "error_message": None,
    }
    assert route_after_planner(state_policy) == "retrieve_policy"


def test_sql_execution_and_self_correction_cycle():
    """Verify SQL error triggers the self-correction cycle back to the planner."""
    broken_state: HydroGridAgentState = {
        "messages": [HumanMessage(content="Check readings")],
        "generated_sql": "SELECT invalid_column FROM pg_dw.warehouse.dim_asset;",
        "sql_query_result": None,
        "policy_context": None,
        "iteration_count": 1,
        "error_message": None,
    }

    result = sql_execution_node(broken_state)
    assert result["error_message"] is not None
    assert any(
        err in result["error_message"]
        for err in ["invalid_column", "Binder Error", "Catalog Error"]
    )

    broken_state["error_message"] = result["error_message"]
    broken_state["iteration_count"] = 1
    next_node = route_after_sql(broken_state)
    assert next_node == "planner", f"Expected 'planner' for self-correction, got: {next_node}"


def test_circuit_breaker_trips_at_max_iterations():
    """Verify loop guard trips when iteration_count >= 3 to prevent infinite cycles."""
    failing_state: HydroGridAgentState = {
        "messages": [HumanMessage(content="Check readings")],
        "generated_sql": "SELECT invalid_col FROM pg_dw.warehouse.dim_asset;",
        "sql_query_result": None,
        "policy_context": None,
        "iteration_count": 3,
        "error_message": "Persistent Binder Error: Column does not exist",
    }

    next_node = route_after_sql(failing_state)
    assert next_node == "synthesizer", (
        f"Circuit breaker failed to trip: expected 'synthesizer', got '{next_node}'"
    )