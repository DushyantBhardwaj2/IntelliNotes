import re
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.state import AgentState
from app.core.llm import chat
from app.core.prompts import ROUTER_PROMPT
from app.ingestion import vectorstore

VALID_ROUTES = ("notes", "web", "direct")

_GREETING_RE = re.compile(r"\b(hi|hello|hey|thanks|thank you)\b", re.IGNORECASE)
_DIRECT_PHRASES = (
    "who are you",
    "how are you",
    "good morning",
    "good afternoon",
    "good evening",
)
_WEB_HINTS = (
    "latest",
    "today",
    "current",
    "news",
    "weather",
    "price",
    "prices",
    "stock",
    "stocks",
    "score",
    "scores",
    "recent",
    "right now",
    "this week",
    "this month",
    "search online",
    "web search",
    "on the internet",
)


def heuristic_route(question: str) -> str:
    """Deterministic keyword fallback used when the routing LLM is unavailable."""
    q = question.lower()
    if _GREETING_RE.search(q) or any(phrase in q for phrase in _DIRECT_PHRASES):
        return "direct"
    if any(hint in q for hint in _WEB_HINTS):
        return "web"
    return "notes"


class RouteDecision(BaseModel):
    route: Literal["notes", "web", "direct"]
    reason: str = Field(description="One short sentence explaining the choice")


def decide_route(question: str, recent_context: str | None = None) -> RouteDecision:
    prompt_content = question
    if recent_context:
        prompt_content = f"Recent conversation context:\n{recent_context}\n\nCurrent user question:\n{question}"

    try:
        return chat(
            [("system", ROUTER_PROMPT), ("human", prompt_content)],
            schema=RouteDecision,
        )
    except Exception:
        # Model outage (quota, network, 5xx): degrade to the deterministic
        # keyword heuristic instead of failing the whole conversation.
        return RouteDecision(
            route=heuristic_route(question),
            reason="Router model unavailable; classified with keyword heuristic fallback.",
        )


def router_node(state: AgentState) -> dict:
    question = state["question"]
    web_enabled = state.get("web_enabled", True)
    doc_id = state.get("doc_id")
    messages = state.get("messages", [])

    # Extract last couple of conversational context lines if multi-turn
    recent_context = ""
    if len(messages) > 1:
        history_snippets = []
        for msg in messages[-3:-1]:
            sender = "User" if msg.type == "human" else "Assistant"
            text = msg.content if isinstance(msg.content, str) else str(msg.content)
            history_snippets.append(f"{sender}: {text[:150]}")
        recent_context = "\n".join(history_snippets)

    decision = decide_route(question, recent_context=recent_context or None)
    route = decision.route if decision.route in VALID_ROUTES else "notes"
    reason = decision.reason

    # If route is notes but no documents exist at all
    total_docs = vectorstore.count_chunks(doc_id)
    if route == "notes" and total_docs == 0:
        if web_enabled:
            route = "web"
            reason = f"No documents in knowledge base for scope; routing to web search. ({reason})"
        else:
            route = "direct"
            reason = f"No documents uploaded yet and web search is disabled. ({reason})"

    elif route == "web" and not web_enabled:
        route = "notes"
        reason = f"{reason} (web search disabled by user, falling back to notes)"

    return {
        "route": route,
        "documents": [],
        "web_results": [],
        "context_sufficient": False,
        "grounding_verdict": "pending",
        "trace": [
            {
                "step": "router",
                "decision": route,
                "reason": reason,
                "question": question,
                "doc_id": doc_id,
            }
        ],
    }

