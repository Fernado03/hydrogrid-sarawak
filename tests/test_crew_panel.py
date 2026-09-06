"""Verification tests for Phase 6 CrewAI Strategic Panel setup."""

from __future__ import annotations
import pytest
from crewai import Agent, Crew, Process

from hydrogrid.agents.crew_panel import (
    build_strategic_committee,
    create_dispatch_engineer,
    create_energy_economist,
    create_hydrogen_lead,
    get_crew_llm,
    sql_tool,
    policy_tool,
)
from hydrogrid.config import load_settings


def test_crew_tools_execution():
    """Verify CrewAI tools wrap underlying HydroGrid tools correctly."""
    # Test safe SQL tool rejects unsafe input
    sql_res = sql_tool.run("DROP TABLE warehouse.dim_asset;")
    assert "ERROR" in sql_res

    # Test policy tool retrieves Bakun rule
    pol_res = policy_tool.run("Bakun reservoir flood safety")
    assert "212m" in pol_res


def test_agent_personas_configuration():
    """Verify agents instantiate with correct roles, goals, and tool allowances."""
    settings = load_settings()
    llm = get_crew_llm(settings=settings)

    dispatcher = create_dispatch_engineer(llm)
    assert isinstance(dispatcher, Agent)
    assert "Dispatch" in dispatcher.role
    assert len(dispatcher.tools) == 2  # SQL + Policy

    economist = create_energy_economist(llm)
    assert isinstance(economist, Agent)
    assert "Economist" in economist.role
    assert len(economist.tools) == 2  # SQL + Policy

    h2_lead = create_hydrogen_lead(llm)
    assert isinstance(h2_lead, Agent)
    assert "Hydrogen" in h2_lead.role
    assert len(h2_lead.tools) == 1  # Policy only


def test_build_strategic_committee_topology():
    """Verify committee crew compiles with sequential process and ordered tasks."""
    scenario = "Heavy monsoonal inflow at Bakun coinciding with peak industrial demand."
    crew = build_strategic_committee(scenario)

    assert isinstance(crew, Crew)
    assert len(crew.agents) == 3
    assert len(crew.tasks) == 3
    assert crew.process == Process.sequential

    # Assert sequential task chain alignment
    assert crew.tasks[0].agent.role == crew.agents[0].role  # Dispatcher
    assert crew.tasks[1].agent.role == crew.agents[1].role  # Economist
    assert crew.tasks[2].agent.role == crew.agents[2].role  # Hydrogen Lead