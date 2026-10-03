from unittest.mock import patch
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.message import add_messages

from app.agent.router import RouteDecision, decide_route, heuristic_route, router_node
from app.agent.grader import GradeDecision, grade_node
from app.agent.grounding import (
    GroundingDecision,
    grounding_check_node,
    looks_like_refusal,
)
from app.agent.retriever import condense_question, retrieve_node
from app.agent.synthesize import INSUFFICIENT_CONTEXT_NOTE, synthesize_node
from app.agent.graph import build_graph


@patch("app.agent.router.decide_route")
@patch("app.agent.router.vectorstore.count_chunks", return_value=5)
def test_router_node_notes_path(mock_count, mock_decide):
    mock_decide.return_value = RouteDecision(
        route="notes", reason="Query asks about document contents."
    )
    state = {"question": "What is the thesis of chapter 1?", "web_enabled": True}
    result = router_node(state)

    assert result["route"] == "notes"
    assert len(result["trace"]) == 1
    assert result["trace"][0]["step"] == "router"
    assert result["trace"][0]["decision"] == "notes"


@patch("app.agent.router.decide_route")
@patch("app.agent.router.vectorstore.count_chunks", return_value=0)
def test_router_node_empty_store_fallback(mock_count, mock_decide):
    mock_decide.return_value = RouteDecision(
        route="notes", reason="Query asks about document contents."
    )
    state = {"question": "What is chapter 1 about?", "web_enabled": True}
    result = router_node(state)

    # When store has 0 chunks and web is enabled, routes to web search fallback
    assert result["route"] == "web"
    assert "No documents in knowledge base" in result["trace"][0]["reason"]


def test_grade_node_no_documents():
    state = {"question": "What is the conclusion?", "documents": [], "trace": []}
    result = grade_node(state)
    assert result["context_sufficient"] is False
    assert result["trace"][-1]["decision"] == "insufficient"


@patch("app.agent.grader.chat")
def test_grade_node_with_documents(mock_chat):
    mock_chat.return_value = GradeDecision(
        sufficient=True, reason="Excerpts clearly explain the topic."
    )
    state = {
        "question": "What is RAG?",
        "documents": [
            {
                "text": "RAG stands for Retrieval-Augmented Generation.",
                "metadata": {"filename": "rag.pdf", "page_number": 1, "chunk_index": 0},
            }
        ],
        "trace": [],
    }
    result = grade_node(state)
    assert result["context_sufficient"] is True
    assert result["trace"][-1]["decision"] == "sufficient"


@patch("app.agent.grader.chat")
def test_grade_node_model_error_defaults_sufficient(mock_chat):
    mock_chat.side_effect = RuntimeError("429 quota exceeded")
    state = {
        "question": "What is RAG?",
        "documents": [
            {
                "text": "RAG stands for Retrieval-Augmented Generation.",
                "metadata": {"filename": "rag.pdf", "page_number": 1, "chunk_index": 0},
            }
        ],
        "trace": [],
    }
    result = grade_node(state)
    assert result["context_sufficient"] is True
    reason = result["trace"][-1]["reason"]
    assert "Grader model unavailable" in reason
    assert "429 quota exceeded" in reason


def test_grounding_check_node_skipped_on_direct():
    state = {
        "route": "direct",
        "answer": "Hello! How can I help you?",
        "documents": [],
        "web_results": [],
        "trace": [],
    }
    result = grounding_check_node(state)
    assert result["grounding_verdict"] == "skipped"
    # Even on the skip path, the final assistant message must be persisted
    assert len(result["messages"]) == 1
    assert result["messages"][0].content == "Hello! How can I help you?"


@patch("app.agent.grounding.chat")
def test_grounding_check_node_verified(mock_chat):
    mock_chat.return_value = GroundingDecision(
        grounded=True, reason="All facts match retrieved excerpts."
    )
    state = {
        "route": "notes",
        "answer": "RAG combines retrieval with generative models [Document: notes.pdf, Page: 1].",
        "documents": [
            {
                "text": "RAG combines retrieval with generative models.",
                "metadata": {"filename": "notes.pdf", "page_number": 1, "chunk_index": 0},
            }
        ],
        "web_results": [],
        "trace": [],
    }
    result = grounding_check_node(state)
    assert result["grounding_verdict"] == "verified"
    assert result["answer"] == state["answer"]
    assert result["trace"][-1]["status"] == "verified"
    assert len(result["messages"]) == 1
    assert result["messages"][0].content == state["answer"]


@patch("app.agent.grounding.chat")
def test_grounding_check_node_corrected(mock_chat):
    mock_chat.return_value = GroundingDecision(
        grounded=False,
        reason="Claim about 99% accuracy was unsupported.",
        corrected_answer="RAG combines retrieval with generative models.",
    )
    state = {
        "route": "notes",
        "answer": "RAG combines retrieval with generative models and achieves 99% accuracy on all tasks.",
        "documents": [
            {"text": "RAG combines retrieval with generative models.", "metadata": {}}
        ],
        "web_results": [],
        "trace": [],
    }
    result = grounding_check_node(state)
    assert result["grounding_verdict"] == "corrected"
    assert result["answer"] == "RAG combines retrieval with generative models."
    assert result["trace"][-1]["status"] == "corrected"
    # Exactly ONE final assistant message, containing the corrected answer
    assert len(result["messages"]) == 1
    assert result["messages"][0].content == "RAG combines retrieval with generative models."


@patch("app.agent.grounding.chat")
def test_grounding_check_node_unverified_without_correction(mock_chat):
    """grounded=False with no corrected_answer must NOT claim 'corrected'."""
    mock_chat.return_value = GroundingDecision(
        grounded=False,
        reason="Claim about 99% accuracy was unsupported.",
        corrected_answer=None,
    )
    state = {
        "route": "notes",
        "answer": "RAG combines retrieval with generative models and achieves 99% accuracy.",
        "documents": [
            {"text": "RAG combines retrieval with generative models.", "metadata": {}}
        ],
        "web_results": [],
        "trace": [],
    }
    result = grounding_check_node(state)
    assert result["grounding_verdict"] == "unverified"
    assert result["answer"] == state["answer"]
    assert result["trace"][-1]["status"] == "unverified"
    assert "warning" in result["trace"][-1]["detail"]
    assert len(result["messages"]) == 1


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The provided documents do not contain that information.", True),
        ("No information about the bonus was found in the guide.", True),
        ("This topic is not mentioned anywhere in the notes.", True),
        ("The Atlas Protocol operates on port 5050.", False),
        ("Revenue was 4.2 million dollars.", False),
    ],
)
def test_looks_like_refusal(text, expected):
    assert looks_like_refusal(text) is expected


@patch("app.agent.grounding.chat")
def test_grounding_rejects_correction_that_strips_refusal(mock_chat):
    """Deterministic net: a correction that replaces an honest refusal with
    new content must be rejected; the refusal is kept and flagged unverified."""
    original = (
        "The provided document(s) do not contain information to answer this question."
    )
    mock_chat.return_value = GroundingDecision(
        grounded=False,
        reason="The context contains details the answer ignored.",
        corrected_answer=(
            "The Atlas Protocol operates on port 5050, uses AES-256 encryption, "
            "rotates keys weekly, and is audited quarterly."
        ),
    )
    state = {
        "route": "notes",
        "answer": original,
        "documents": [
            {"text": "Atlas Protocol facts...", "metadata": {}}
        ],
        "web_results": [],
        "trace": [],
    }
    result = grounding_check_node(state)
    assert result["grounding_verdict"] == "unverified"
    assert result["answer"] == original
    assert "Correction rejected" in result["trace"][-1]["detail"]
    assert "5050" not in result["answer"]


@patch("app.agent.grounding.chat")
def test_grounding_accepts_correction_that_keeps_refusal(mock_chat):
    original = "The guide does not mention a CEO bonus, and RAG achieves 99% accuracy."
    mock_chat.return_value = GroundingDecision(
        grounded=False,
        reason="The 99% accuracy claim is unsupported.",
        corrected_answer="The guide does not mention a CEO bonus.",
    )
    state = {
        "route": "notes",
        "answer": original,
        "documents": [{"text": "No bonus info.", "metadata": {}}],
        "web_results": [],
        "trace": [],
    }
    result = grounding_check_node(state)
    assert result["grounding_verdict"] == "corrected"
    assert result["answer"] == "The guide does not mention a CEO bonus."


@patch("app.agent.synthesize.chat")
@patch("app.agent.grounding.chat")
def test_grounding_correction_replaces_history_not_appends(
    mock_grounding_chat, mock_synthesize_chat
):
    """Regression test: after a grounding correction, the conversation history
    must contain exactly one assistant message per turn — the corrected one —
    and never the hallucinated original."""
    mock_synthesize_chat.return_value = AIMessage(
        content="RAG combines retrieval with generative models and achieves 99% accuracy on all tasks."
    )
    mock_grounding_chat.return_value = GroundingDecision(
        grounded=False,
        reason="Claim about 99% accuracy was unsupported.",
        corrected_answer="RAG combines retrieval with generative models.",
    )
    state = {
        "messages": [HumanMessage(content="What is RAG and how accurate is it?")],
        "question": "What is RAG and how accurate is it?",
        "route": "notes",
        "documents": [
            {
                "text": "RAG combines retrieval with generative models.",
                "metadata": {"filename": "notes.pdf", "page_number": 1, "chunk_index": 0},
            }
        ],
        "web_results": [],
        "trace": [],
    }

    synth_updates = synthesize_node(state)
    assert "messages" not in synth_updates
    state.update(synth_updates)

    grounding_updates = grounding_check_node(state)
    merged_messages = add_messages(state["messages"], grounding_updates["messages"])

    assert [m.type for m in merged_messages] == ["human", "ai"]
    assert len(merged_messages) == 2
    assert "99% accuracy" not in merged_messages[-1].content
    assert merged_messages[-1].content == "RAG combines retrieval with generative models."


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Hello there!", "direct"),
        ("hi", "direct"),
        ("thanks for the help", "direct"),
        ("What is the latest AI news?", "web"),
        ("stock price of apple today", "web"),
        ("search online for the weather in Tokyo", "web"),
        ("Summarize the key points of chapter 2", "notes"),
        ("What does my document say about encryption?", "notes"),
    ],
)
def test_heuristic_route(question, expected):
    assert heuristic_route(question) == expected


@patch("app.agent.router.chat")
def test_decide_route_falls_back_to_heuristic_on_model_error(mock_chat):
    mock_chat.side_effect = RuntimeError("model unavailable")
    decision = decide_route("What is the latest news today?")
    assert decision.route == "web"
    assert "heuristic fallback" in decision.reason


def _synthesize_state(**overrides):
    state = {
        "messages": [HumanMessage(content="What is the CEO's bonus?")],
        "question": "What is the CEO's bonus?",
        "route": "notes",
        "documents": [
            {
                "text": "The Atlas Protocol operates on port 5050 and uses AES-256 encryption.",
                "metadata": {"filename": "atlas.pdf", "page_number": 1, "chunk_index": 0},
            }
        ],
        "web_results": [],
        "context_sufficient": True,
        "trace": [],
    }
    state.update(overrides)
    return state


@patch("app.agent.synthesize.chat")
def test_synthesize_node_appends_insufficient_context_note(mock_chat):
    """Grader said insufficient + no web results: the system prompt must carry
    the explicit anti-pivot instruction."""
    mock_chat.return_value = AIMessage(content="The document does not contain that information.")
    state = _synthesize_state(context_sufficient=False)
    synthesize_node(state)
    system_message = mock_chat.call_args[0][0][0]
    assert INSUFFICIENT_CONTEXT_NOTE in system_message.content


@patch("app.agent.synthesize.chat")
def test_synthesize_node_skips_note_when_sufficient(mock_chat):
    mock_chat.return_value = AIMessage(content="Port 5050.")
    synthesize_node(_synthesize_state(context_sufficient=True))
    system_message = mock_chat.call_args[0][0][0]
    assert INSUFFICIENT_CONTEXT_NOTE not in system_message.content


@patch("app.agent.synthesize.chat")
def test_synthesize_node_skips_note_when_web_results_rescued(mock_chat):
    """Insufficient notes but web fallback produced results: normal synthesis."""
    mock_chat.return_value = AIMessage(content="Answer from web.")
    state = _synthesize_state(
        context_sufficient=False,
        web_results=[{"title": "t", "url": "u", "content": "c"}],
    )
    synthesize_node(state)
    system_message = mock_chat.call_args[0][0][0]
    assert INSUFFICIENT_CONTEXT_NOTE not in system_message.content


def test_build_graph_structure():
    graph = build_graph()
    # Ensure all nodes exist in the compiled graph
    assert "router" in graph.nodes
    assert "retrieve" in graph.nodes
    assert "grade" in graph.nodes
    assert "web_search" in graph.nodes
    assert "synthesize" in graph.nodes
    assert "grounding_check" in graph.nodes
