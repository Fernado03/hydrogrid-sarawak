"""Agent state definitions for the HydroGrid LangGraph hybrid workflow."""

from __future__ import annotations
from typing import Annotated, Any, Dict, List, Optional, Sequence
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class HydroGridAgentState(TypedDict):
    """Centralized state graph memory for the HydroGrid intelligence agent.

    Attributes:
        messages: Conversation history, append-only reducer via add_messages.
        generated_sql: The latest SQL query authored by the reasoning node.
        sql_query_result: Formatted tabular results from the database execution tool.
        policy_context: Retrieved text chunks from Sarawak Energy policy guidelines.
        iteration_count: Loop guard counter to prevent infinite agent reasoning cycles.
        error_message: Captures syntax or execution exceptions to allow self-correction.
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    generated_sql: Optional[str]
    sql_query_result: Optional[str]
    policy_context: Optional[str]
    iteration_count: int
    error_message: Optional[str]