import sqlite3

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


def get_checkpointer() -> SqliteSaver:
    """Create the SQLite checkpointer backing persistent conversation memory.

    Thread-safety: the connection uses ``check_same_thread=False`` on purpose.
    SqliteSaver serializes every database operation behind an internal
    ``threading.Lock`` and enables WAL journaling during ``setup()``, so
    concurrent FastAPI threadpool workers sharing this single-process saver
    cannot interleave low-level reads/writes. Note that running multiple
    *processes* (e.g. ``uvicorn --workers 4``) against the same SQLite file
    is not supported; swap in PostgresSaver for multi-worker deployments.
    """
    connection = sqlite3.connect(
        str(settings.memory_db_path), check_same_thread=False
    )
    return SqliteSaver(connection)


_GRAPH: CompiledStateGraph | None = None


def get_graph() -> CompiledStateGraph:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph(checkpointer=get_checkpointer())
    return _GRAPH
