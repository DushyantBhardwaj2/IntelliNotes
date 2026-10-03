from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    question: str
    web_enabled: bool
    doc_id: str | None

    route: str
    documents: list[dict]
    web_results: list[dict]
    context_sufficient: bool
    grounding_verdict: str

    answer: str
    trace: list[dict]


def append_trace(state: AgentState, entry: dict) -> list[dict]:
    return list(state.get("trace") or []) + [entry]

