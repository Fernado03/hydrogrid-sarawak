"""Real-Time Operations Command Center for HydroGrid Sarawak."""

from __future__ import annotations
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from langchain_core.messages import HumanMessage

from hydrogrid.agents.crew_panel import build_strategic_committee
from hydrogrid.agents.graph import build_agent_graph
from hydrogrid.config import load_settings
from hydrogrid.db.duckdb_engine import query_duckdb

st.set_page_config(
    page_title="HydroGrid Sarawak | Command Center",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS styling for SCADA-like dark aesthetic
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #1e2530;
        border-radius: 8px;
        padding: 15px;
        border-left: 5px solid #00d26a;
    }
    .stChatMessage {
        border-radius: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def load_agent():
    """Initializes and caches the compiled LangGraph state machine."""
    return build_agent_graph()


st.title("⚡ HydroGrid Sarawak — Grid Operations & Intelligence Hub")
st.caption("Autonomous Telemetry Analytics, Predictive Inflow Modeling & Strategic Dispatch")

# ==========================================
# 1. SIDEBAR: Live Asset Telemetry & Status
# ==========================================
st.sidebar.header("Asset Telemetry Stream")

try:
    telemetry_query = """
        SELECT 
            da.asset_name,
            da.asset_type,
            ft.temperature_2m,
            ft.relative_humidity_2m,
            ft.precipitation,
            ft.global_tilted_irradiance,
            ft.timestamp
        FROM pg_dw.warehouse.fact_telemetry ft
        JOIN pg_dw.warehouse.dim_asset da ON ft.asset_id = da.id
        ORDER BY ft.timestamp DESC
        LIMIT 10;
    """
    rel = query_duckdb(telemetry_query)
    df_live = rel.df()
    latest_ts = df_live["timestamp"].iloc[0] if not df_live.empty else "N/A"
    st.sidebar.success(f"SCADA Sync Active: {latest_ts}")
except Exception:
    df_live = pd.DataFrame()
    st.sidebar.warning("Warehouse telemetry stream offline. Using cached state.")

st.sidebar.markdown("---")
st.sidebar.subheader("Critical Thresholds")
st.sidebar.markdown(
    """
    - **Bakun Max Level:** `228.0 m`
    - **Spillway Warning:** `225.0 m`
    - **Rainfall Alert:** `> 50.0 mm / 24h`
    - **Frequency Target:** `50.00 Hz (±0.2)`
    - **Bintulu Base Quota:** `100 MW`
    """
)

# ==========================================
# 2. TOP METRICS ROW
# ==========================================
col1, col2, col3, col4 = st.columns(4)

with col1:
    fig_gauge = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=225.8,
            title={"text": "Bakun Reservoir (m)"},
            gauge={
                "axis": {"range": [210, 230]},
                "bar": {"color": "#ffaa00"},
                "steps": [
                    {"range": [210, 225], "color": "#1b382b"},
                    {"range": [225, 227], "color": "#5e4b10"},
                    {"range": [227, 230], "color": "#5e1515"},
                ],
                "threshold": {
                    "line": {"color": "red", "width": 4},
                    "thickness": 0.75,
                    "value": 228,
                },
            },
        )
    )
    fig_gauge.update_layout(height=180, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig_gauge, use_container_width=True)

with col2:
    st.metric(
        label="Grid Frequency",
        value="49.98 Hz",
        delta="-0.02 Hz (Turbine Primary Response)",
        delta_color="normal",
    )
    st.metric(
        label="Rolling 24h Rainfall (Bakun)",
        value="62.0 mm",
        delta="ALERT (+12.0 mm over threshold)",
        delta_color="inverse",
    )

with col3:
    st.metric(
        label="Batang Ai Floating Solar",
        value="90 W/m²",
        delta="-310 W/m² (Cloud Obscuration)",
        delta_color="inverse",
    )
    st.metric(
        label="Batang Ai Hydro Response",
        value="20 MW",
        delta="+20 MW Ramped",
        delta_color="normal",
    )

with col4:
    st.metric(
        label="Bintulu H2 Electrolyzers",
        value="100 MW",
        delta="Baseload Quota Maintained",
        delta_color="off",
    )
    st.metric(
        label="Peak Export Margin",
        value="MYR 0.38 / kWh",
        delta="Singapore Interconnection Active",
        delta_color="normal",
    )

# ==========================================
# 3. INTERACTIVE TABS: AGENTS & ANALYTICS
# ==========================================
tab_agent, tab_crew, tab_analytics = st.tabs(
    [
        "🤖 Autonomous SQL & Policy Agent (LangGraph)",
        "🏛️ Strategic Committee Simulator (CrewAI)",
        "📊 Telemetry Explorer (DuckDB)",
    ]
)

# ------------------------------------------
# TAB 1: LangGraph Agent Chat
# ------------------------------------------
with tab_agent:
    st.subheader("Autonomous Dispatcher Console")
    st.caption("Ask natural language questions covering telemetry databases or Sarawak Energy regulatory policies.")

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "HydroGrid Dispatcher ready. Query telemetry analytics or regulatory policies.",
            }
        ]

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_prompt := st.chat_input("Enter grid query (e.g. 'What is the average temperature at Bakun Dam?')"):
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Agent analyzing schemas, generating SQL, and cross-referencing policy..."):
                agent = load_agent()
                state = {
                    "messages": [HumanMessage(content=user_prompt)],
                    "generated_sql": None,
                    "sql_query_result": None,
                    "policy_context": None,
                    "iteration_count": 0,
                    "error_message": None,
                }
                result = agent.invoke(state)

                if result.get("generated_sql"):
                    with st.expander("Inspected SQL Execution"):
                        st.code(result["generated_sql"], language="sql")
                        if result.get("sql_query_result"):
                            st.markdown(result["sql_query_result"])

                if result.get("policy_context"):
                    with st.expander("Retrieved Regulatory Excerpts"):
                        st.markdown(result["policy_context"])

                reply = result["messages"][-1].content
                st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})

# ------------------------------------------
# TAB 2: CrewAI Strategic Committee
# ------------------------------------------
with tab_crew:
    st.subheader("Multi-Agent Strategic Dispatch Panel")
    st.markdown(
        "Convene the **Grid Dispatch Engineer**, **Energy Systems Economist**, and **Hydrogen Logistics Lead** "
        "to resolve multi-objective grid bottlenecks."
    )

    scenario_input = st.text_area(
        "Define Grid Stress Event:",
        value=(
            "CRITICAL GRID EVENT: 24-hour rolling rainfall at Bakun Dam has reached 62.0 mm, "
            "and reservoir level is currently at 225.8 meters (approaching the 228m maximum limit). "
            "Simultaneously, severe cloud cover at Batang Ai has caused solar irradiance to drop to 90 W/m² "
            "at 19:00 hours during evening peak demand. Bintulu Green Hydrogen Hub is currently drawing 100 MW. "
            "Formulate an emergency dispatch and balancing plan adhering to Sarawak Energy policies."
        ),
        height=110,
    )

    if st.button("🚀 Convene Strategic Committee", type="primary"):
        with st.status("Committee in Session...", expanded=True) as status:
            st.write("🧑‍🔧 **Grid Dispatch Engineer** analyzing reservoir hydrodynamics and 50.0 Hz stability...")
            st.write("📈 **Energy Economist** computing spilled water revenue loss vs. peak export margins...")
            st.write("⚗️ **Hydrogen Logistics Lead** reviewing 85% storage quota exemption rules...")

            committee = build_strategic_committee(scenario_description=scenario_input)
            output = committee.kickoff()
            status.update(label="Consensus Dispatch Plan Finalized!", state="complete", expanded=False)

        st.success("Executive Consensus Delivered")
        st.markdown(output.raw if hasattr(output, "raw") else str(output))

# ------------------------------------------
# TAB 3: DuckDB Telemetry Explorer
# ------------------------------------------
with tab_analytics:
    st.subheader("High-Performance Warehouse Analytics (DuckDB)")
    custom_sql = st.text_area(
        "Interactive Read-Only SQL Query (`pg_dw` Catalog):",
        value="SELECT * FROM pg_dw.warehouse.v_telemetry_analytics LIMIT 15;",
        height=90,
    )

    if st.button("Execute Query"):
        try:
            rel = query_duckdb(custom_sql)
            df_result = rel.df()
            st.dataframe(df_result, use_container_width=True)
            st.caption(f"Retrieved {len(df_result)} records via DuckDB zero-copy scan.")
        except Exception as err:
            st.error(f"Execution Error: {err}")