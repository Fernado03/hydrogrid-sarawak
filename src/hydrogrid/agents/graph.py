"""Cyclic LangGraph state machine for hybrid SQL telemetry and policy intelligence."""

from __future__ import annotations
import json
import re
from typing import Any, Dict, Literal, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from hydrogrid.agents.state import HydroGridAgentState
from hydrogrid.agents.tools import (
    execute_safe_sql,
    inspect_warehouse_schema,
    search_sarawak_energy_policy,
)
from hydrogrid.config import Settings, load_settings


def get_llm(settings: Optional[Settings] = None) -> BaseChatModel:
    """Instantiates the ChatOpenAI client using the configured base URL and API key."""
    cfg = settings or load_settings()
    return ChatOpenAI(
        base_url=cfg.llm_base_url,
        api_key=cfg.llm_api_key,
        model="MiniMax-M3",
        temperature=0.0,
    )


AGENT_SYSTEM_PROMPT = """You are the HydroGrid Sarawak Senior Grid Intelligence Dispatcher.
You have access to Sarawak's energy infrastructure telemetry and regulatory policies:
- Assets: Bakun Dam (Hydro), Murum Dam (Hydro), Batang Ai (Floating Solar/Hydro), Bintulu H2 Hub.
- Tables in pg_dw:
  * warehouse.dim_asset (id, asset_name, asset_type, latitude, longitude)
  * warehouse.fact_telemetry (id, asset_id, timestamp, temperature_2m, relative_humidity_2m, precipitation, global_tilted_irradiance)
  * warehouse.v_telemetry_analytics (id, timestamp, asset_name, asset_type, temperature_2m, relative_humidity_2m, precipitation, global_tilted_irradiance, rolling_24h_temp, rolling_24h_precip)
  * marts.daily_telemetry_summary (asset_id, asset_name, asset_type, summary_date, avg_temp_c, total_precip_mm, peak_irradiance_wm2, readings_count)

Always prefix tables with 'pg_dw.' when querying (e.g., pg_dw.warehouse.dim_asset).
Formulate read-only SQL queries or search policy documents to answer the operator accurately.
"""


def planner_node(state: HydroGridAgentState, llm: Optional[BaseChatModel] = None) -> Dict[str, Any]:
    """Analyzes conversation history, generates SQL or identifies policy retrieval needs."""
    active_llm = llm or get_llm()
    messages = list(state.get("messages", []))
    
    # Include error feedback if recovering from a failed SQL execution
    error_context = ""
    if state.get("error_message"):
        error_context = (
            f"\nATTENTION: Your previous SQL query failed with error: {state['error_message']}. "
            "Inspect the table schema carefully, correct the column names or syntax, and formulate a revised query."
        )

    prompt = (
        f"{AGENT_SYSTEM_PROMPT}\n"
        f"Available Schemas:\n{inspect_warehouse_schema()}\n"
        f"{error_context}\n"
        "Respond with a SQL query starting with 'SELECT' or 'WITH' if database telemetry is needed, "
        "or prefix with 'POLICY:' followed by search terms if regulatory rules are needed, "
        "or write your final analysis if you have enough information."
    )

    response = active_llm.invoke([SystemMessage(content=prompt)] + messages)
    content = str(response.content).strip()

    if content.startswith("SELECT") or content.startswith("WITH") or re.search(r"```sql(.*?)```", content, re.DOTALL):
        sql_match = re.search(r"```sql(.*?)```", content, re.DOTALL)
        sql_query = sql_match.group(1).strip() if sql_match else content.strip()
        return {
            "generated_sql": sql_query,
            "error_message": None,
            "iteration_count": state.get("iteration_count", 0) + 1,
        }

    if content.startswith("POLICY:"):
        search_phrase = content[len("POLICY:"):].strip()
        return {
            "policy_search_phrase": search_phrase,
            "iteration_count": state.get("iteration_count", 0) + 1,
        }
    
    return {
        "iteration_count": state.get("iteration_count", 0) + 1,
        "error_message": None,
    }


def sql_execution_node(state: HydroGridAgentState) -> Dict[str, Any]:
    """Executes the authored SQL query via execute_safe_sql and records the result."""
    sql = state.get("generated_sql")
    if not sql:
        return {"sql_query_result": None, "error_message": "No SQL query authored to execute."}

    executed_result = execute_safe_sql(sql)
    if executed_result.startswith("ERROR") or "Binder Error" in executed_result or "Parser Error" in executed_result:
        return {"sql_query_result": None, "error_message": executed_result}
    return {"sql_query_result": executed_result, "error_message": None}


def policy_retriever_node(state: HydroGridAgentState) -> Dict[str, Any]:
    """Retrieves Sarawak Energy operational rules based on the user's latest query."""
    user_query = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            user_query = str(msg.content)
            break

    retrieved_policy = search_sarawak_energy_policy(user_query)
    return {"policy_context": retrieved_policy, "error_message": None}


def synthesizer_node(state: HydroGridAgentState, llm: Optional[BaseChatModel] = None) -> Dict[str, Any]:
    """Synthesizes database telemetry results and regulatory policies into an operational response."""
    active_llm = llm or get_llm()

    synthesis_prompt = (
        f"{AGENT_SYSTEM_PROMPT}\n\n"
        f"Database Query Executed: {state.get('generated_sql') or 'None'}\n"
        f"Telemetry Data:\n{state.get('sql_query_result') or 'No telemetry queried.'}\n\n"
        f"Policy Guidelines:\n{state.get('policy_context') or 'No specific policy retrieved.'}\n\n"
        "Provide a concise, professional operational briefing synthesizing the data and policy compliance."
    )

    response = active_llm.invoke([SystemMessage(content=synthesis_prompt)] + list(state.get("messages", [])))
    return {
        "messages": [response],
        "error_message": None,
    }


def route_after_planner(state: HydroGridAgentState) -> Literal["execute_sql", "retrieve_policy", "synthesizer"]:
    """Conditional router directing state to SQL execution, policy RAG, or synthesis."""
    if state.get("generated_sql") and not state.get("sql_query_result"):
        return "execute_sql"

    if state.get("policy_context") is None:
        user_query = ""
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, HumanMessage):
                user_query = str(msg.content).lower()
                break

        policy_keywords = [
            "policy", "rule", "safety", "limit", "flood", "protocol",
            "quota", "framework", "regulatory", "guideline", "threshold",
        ]
        if any(kw in user_query for kw in policy_keywords) or state.get("policy_search_phrase"):
            return "retrieve_policy"

    return "synthesizer"


def route_after_sql(state: HydroGridAgentState) -> Literal["planner", "retrieve_policy", "synthesizer"]:
    """Conditional router enabling self-correction loop, policy retrieval, or synthesis."""
    # 1. Self-correction loop if SQL failed
    if state.get("error_message") and state.get("iteration_count", 0) < 3:
        return "planner"

    # 2. Check if policy context is still needed
    if state.get("policy_context") is None:
        user_query = ""
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, HumanMessage):
                user_query = str(msg.content).lower()
                break

        policy_keywords = [
            "policy", "rule", "safety", "limit", "flood", "protocol",
            "quota", "framework", "regulatory", "guideline", "threshold",
        ]
        if any(kw in user_query for kw in policy_keywords):
            return "retrieve_policy"

    return "synthesizer"


def build_agent_graph(llm: Optional[BaseChatModel] = None) -> StateGraph:
    """Constructs and compiles the cyclic LangGraph state machine."""
    workflow = StateGraph(HydroGridAgentState)

    def _planner(state: HydroGridAgentState):
        return planner_node(state, llm=llm)

    def _synthesizer(state: HydroGridAgentState):
        return synthesizer_node(state, llm=llm)

    workflow.add_node("planner", _planner)
    workflow.add_node("execute_sql", sql_execution_node)
    workflow.add_node("retrieve_policy", policy_retriever_node)
    workflow.add_node("synthesizer", _synthesizer)

    workflow.add_edge(START, "planner")

    workflow.add_conditional_edges(
        "planner",
        route_after_planner,
        {
            "execute_sql": "execute_sql",
            "retrieve_policy": "retrieve_policy",
            "synthesizer": "synthesizer",
        },
    )

    workflow.add_conditional_edges(
        "execute_sql",
        route_after_sql,
        {
            "planner": "planner",
            "retrieve_policy": "retrieve_policy",  # Added routing edge
            "synthesizer": "synthesizer",
        },
    )

    workflow.add_edge("retrieve_policy", "synthesizer")
    workflow.add_edge("synthesizer", END)

    return workflow.compile()


if __name__ == "__main__":
    from datetime import datetime, timedelta
    from sqlalchemy.orm import sessionmaker
    from hydrogrid.db.engine import get_postgres_engine
    from hydrogrid.db.base import Base
    from hydrogrid.db.models import DimAsset, FactTelemetry
    from hydrogrid.warehouse.analytics import create_analytics_views

    cfg = load_settings()
    engine = get_postgres_engine(cfg)
    Base.metadata.create_all(engine)
    create_analytics_views(engine)

    # Ensure Bakun asset and telemetry exist
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    bakun = session.query(DimAsset).filter_by(asset_name="Bakun Dam").first()
    if not bakun:
        bakun = DimAsset(asset_name="Bakun Dam", asset_type="Hydro", latitude=2.75, longitude=114.05)
        session.add(bakun)
        session.commit()

    if session.query(FactTelemetry).filter_by(asset_id=bakun.id).count() == 0:
        base_time = datetime.utcnow()
        for h in range(48):
            session.add(
                FactTelemetry(
                    asset_id=bakun.id,
                    timestamp=base_time - timedelta(hours=h),
                    temperature_2m=27.5 + (h % 3),
                    relative_humidity_2m=82.0,
                    precipitation=12.0 if h == 4 else 0.5,
                    global_tilted_irradiance=450.0 if 8 <= (h % 24) <= 16 else 0.0,
                )
            )
        session.commit()
    session.close()

    print("\n=======================================================")
    print("   HYDROGRID SARAWAK — AUTONOMOUS DISPATCH AGENT")
    print("=======================================================\n")

    agent = build_agent_graph()
    sample_query = (
        "What is the average temperature at Bakun Dam, and "
        "what are the severe rainfall alert thresholds for reservoir safety?"
    )
    print(f"Operator Query: {sample_query}\n")
    print("Executing cyclic agent workflow...\n")

    initial_state = {
        "messages": [HumanMessage(content=sample_query)],
        "generated_sql": None,
        "sql_query_result": None,
        "policy_context": None,
        "iteration_count": 0,
        "error_message": None,
    }

    final_state = agent.invoke(initial_state)

    print("\n--- Generated SQL ---")
    print(final_state.get("generated_sql") or "None")

    print("\n--- SQL Query Results ---")
    print(final_state.get("sql_query_result") or "No telemetry queried.")

    print("\n--- Policy Excerpts Retrieved ---")
    print(final_state.get("policy_context") or "No policy context retrieved.")

    print("\n================ FINAL AGENT DISPATCH BRIEFING ================")
    print(final_state["messages"][-1].content)
    print("===============================================================\n")