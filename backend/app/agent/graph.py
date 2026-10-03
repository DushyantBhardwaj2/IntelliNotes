import os
import sqlite3
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.grader import grade_node
from app.agent.grounding import grounding_check_node
from app.agent.retriever import retrieve_node
from app.agent.router import router_node
from app.agent.state import AgentState
from app.agent.synthesize import synthesize_node
from app.agent.websearch import web_search_node
from app.config import settings


def route_after_router(state: AgentState) -> str:
    return {"notes": "retrieve", "web": "web_search", "direct": "synthesize"}[
        state.get("route", "notes")
    ]


def route_after_grade(state: AgentState) -> str:
    if state.get("context_sufficient"):
        return "synthesize"
    if state.get("web_enabled", True):
        return "web_search"
    return "synthesize"


def build_graph(checkpointer=None) -> CompiledStateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("router", router_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("grade", grade_node)
    builder.add_node("web_search", web_search_node)
    builder.add_node("synthesize", synthesize_node)
    builder.add_node("grounding_check", grounding_check_node)

    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router",
        route_after_router,
        {"retrieve": "retrieve", "web_search": "web_search", "synthesize": "synthesize"},
    )
    builder.add_edge("retrieve", "grade")
    builder.add_conditional_edges(
        "grade",
        route_after_grade,
        {"web_search": "web_search", "synthesize": "synthesize"},
    )
    builder.add_edge("web_search", "synthesize")
    builder.add_edge("synthesize", "grounding_check")
    builder.add_edge("grounding_check", END)

    return builder.compile(checkpointer=checkpointer)


_CHECKPOINTER: Any | None = None
_PG_POOL: Any | None = None
_PG_SETUP_DONE: bool = False


def get_checkpointer() -> Any:
    """Create the checkpointer backing persistent conversation memory.

    When DATABASE_URL is configured (e.g. Neon in production), PostgresSaver
    is used with connection pooling and idempotent setup.
    Otherwise, returns SqliteSaver for local development and tests.
    """
    global _CHECKPOINTER, _PG_POOL, _PG_SETUP_DONE
    if _CHECKPOINTER is not None:
        return _CHECKPOINTER

    db_url = settings.database_url.strip() or os.environ.get("DATABASE_URL", "").strip()
    if db_url:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        _PG_POOL = ConnectionPool(
            conninfo=db_url,
            max_size=10,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        saver = PostgresSaver(_PG_POOL)
        if not _PG_SETUP_DONE:
            try:
                saver.setup()
                _PG_SETUP_DONE = True
            except Exception as exc:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).warning("PostgresSaver setup check: %s", exc)
                _PG_SETUP_DONE = True
        _CHECKPOINTER = saver
        return _CHECKPOINTER

    connection = sqlite3.connect(
        str(settings.memory_db_path), check_same_thread=False
    )
    _CHECKPOINTER = SqliteSaver(connection)
    return _CHECKPOINTER


_GRAPH: CompiledStateGraph | None = None


def get_graph() -> CompiledStateGraph:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph(checkpointer=get_checkpointer())
    return _GRAPH

