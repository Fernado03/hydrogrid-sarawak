"""Multi-Agent Strategic Intelligence Panel for HydroGrid Sarawak using CrewAI."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from crewai import Agent, Crew, Process, Task, LLM
from crewai.tools import tool

from hydrogrid.agents.tools import execute_safe_sql, search_sarawak_energy_policy
from hydrogrid.config import Settings, load_settings


# 1. Wrap Phase 5 tools for CrewAI
@tool("Warehouse SQL Query Tool")
def sql_tool(query: str) -> str:
    """Executes safe, read-only SQL queries via DuckDB against warehouse and marts tables."""
    return execute_safe_sql(query)


@tool("Sarawak Energy Regulatory Policy Search")
def policy_tool(search_query: str) -> str:
    """Searches Sarawak Energy regulatory policies, dam safety limits, and hydrogen frameworks."""
    return search_sarawak_energy_policy(search_query)


def get_crew_llm(settings: Optional[Settings] = None) -> LLM:
    """Configures the unified CrewAI LLM instance pointing to the configured endpoint."""
    cfg = settings or load_settings()
    return LLM(
        model="glm-5.3-flash",
        base_url=cfg.llm_base_url,
        api_key=cfg.llm_api_key,
        temperature=0.1,
    )


def create_dispatch_engineer(llm: LLM) -> Agent:
    """Instantiates the Grid Dispatch Engineer persona."""
    return Agent(
        role="Senior Grid Dispatch & Safety Engineer",
        goal="Ensure 50.0 Hz grid frequency stability, prevent dam overtopping, and maintain transmission line safety.",
        backstory=(
            "You have 20 years of experience managing Sarawak's hydro cascade across Bakun and Murum. "
            "You are deeply conservative regarding reservoir level limits (212m-228m) and 24h rolling rainfall "
            "thresholds (>50.0 mm). You treat grid physical integrity as an absolute priority over financial gain."
        ),
        tools=[sql_tool, policy_tool],
        llm=llm,
        verbose=True,
    )


def create_energy_economist(llm: LLM) -> Agent:
    """Instantiates the Energy Systems Economist persona."""
    return Agent(
        role="Renewable Energy Market Economist",
        goal="Maximize revenue (MYR/MWh), minimize spilled water economic losses, and optimize peak tariff dispatch.",
        backstory=(
            "You are an expert on ASEAN grid interconnection and Sarawak's industrial power purchase agreements. "
            "You view spilled water as unmonetized capital loss. You constantly seek to keep hydro generation at maximum "
            "profitable capacity while steering power toward high-value industrial and export off-takers."
        ),
        tools=[sql_tool, policy_tool],
        llm=llm,
        verbose=True,
    )


def create_hydrogen_lead(llm: LLM) -> Agent:
    """Instantiates the Hydrogen Logistics Lead persona."""
    return Agent(
        role="Bintulu Green Hydrogen Systems Lead",
        goal="Protect the 100 MW baseload electrolyzer quota and optimize green H2 storage schedules.",
        backstory=(
            "You lead operations at the Bintulu Green Hydrogen Hub. Your ammonia and export off-take contracts "
            "with international buyers penalize delivery shortfalls. You defend your 100 MW hydro power allocation "
            "and ensure electrolyzer ramping stays within Sarawak's energy transition policy limits."
        ),
        tools=[policy_tool],
        llm=llm,
        verbose=True,
    )


def build_strategic_committee(
    scenario_description: str,
    settings: Optional[Settings] = None,
) -> Crew:
    """Assembles the agents, assigns tasks, and constructs the Crew."""
    llm = get_crew_llm(settings=settings)

    # 1. Instantiate the 3 Agent Personas
    dispatcher = create_dispatch_engineer(llm)
    economist = create_energy_economist(llm)
    hydrogen_lead = create_hydrogen_lead(llm)

    task_technical_assessment = Task(
        description=f"Analyze the scenario: {scenario_description}, inspect telemetry or safety policies, and produce a technical safety briefing.",
        expected_output="Markdown briefing covering dam levels, frequency risks, and recommended turbine dispatch.",
        agent=dispatcher,
    )

    task_economic_evaluation = Task(
        description=f"Review the technical recommendations from the dispatcher and assess the revenue impact (MYR), export tariffs, and spill risks for the scenario: {scenario_description}.",
        expected_output="Economic critique quantifying financial trade-offs of the dispatcher's plan.",
        agent=economist,
    )

    task_consensus_plan = Task(
        description=f"Synthesize technical safety limits and economic priorities for the scenario: {scenario_description} while ensuring Bintulu H2 Hub quotas are met.",
        expected_output="Final executive consensus dispatch plan with specific MW allocations for Hydro, Solar, and Hydrogen.",
        agent=hydrogen_lead,
    )

    return Crew(
        agents=[dispatcher, economist, hydrogen_lead],
        tasks=[task_technical_assessment, task_economic_evaluation, task_consensus_plan],
        process=Process.sequential,
        verbose=True,
    )

if __name__ == "__main__":
    print("\n=======================================================")
    print(" HYDROGRID SARAWAK — STRATEGIC DISPATCH COMMITTEE")
    print("=======================================================\n")

    scenario = (
        "CRITICAL GRID EVENT: 24-hour rolling rainfall at Bakun Dam has reached 62.0 mm, "
        "and reservoir level is currently at 225.8 meters (approaching the 228m maximum limit). "
        "Simultaneously, severe cloud cover at Batang Ai has caused solar irradiance to drop to 90 W/m² "
        "at 19:00 hours during evening peak demand. Bintulu Green Hydrogen Hub is currently drawing 100 MW. "
        "Formulate an emergency dispatch and balancing plan adhering to Sarawak Energy policies."
    )

    print(f"Scenario Overview:\n{scenario}\n")
    print("Convening Committee: Grid Dispatcher, Energy Economist, and Hydrogen Systems Lead...\n")

    committee = build_strategic_committee(scenario_description=scenario)
    result = committee.kickoff()

    print("\n=======================================================")
    print("           EXECUTIVE CONSENSUS DISPATCH PLAN")
    print("=======================================================")
    print(result)