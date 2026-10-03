import re

from app.agent.state import AgentState, append_trace
from app.core.llm import chat, to_text
from app.core.prompts import CONDENSE_PROMPT
from app.ingestion import vectorstore


def condense_question(messages: list, question: str) -> str:
    if len(messages) <= 1:
        return question
    try:
        reply = chat([("system", CONDENSE_PROMPT)] + list(messages))
        condensed = to_text(reply).strip()
        # Clean quotes or conversational prefixes
        condensed = re.sub(r'^(Query|Question|Standalone query):\s*', '', condensed, flags=re.IGNORECASE)
        condensed = condensed.strip('"').strip("'").strip()
        return condensed or question
    except Exception:
        return question


def retrieve_node(state: AgentState) -> dict:
    original = state["question"]
    messages = state.get("messages", [])
    doc_id = state.get("doc_id")
    question = condense_question(messages, original)

    documents = vectorstore.search_notes(question, doc_id=doc_id)

    entry = {
        "step": "retrieve",
        "detail": f"{len(documents)} chunk(s) retrieved from notes",
        "question_used": question,
        "doc_id": doc_id,
        "sources": [
            {
                "filename": doc["metadata"].get("filename", "unknown"),
                "page": doc["metadata"].get("page_number", 1),
                "chunk": doc["metadata"].get("chunk_index", 0),
            }
            for doc in documents
        ],
    }
    return {
        "question": question,
        "documents": documents,
        "trace": append_trace(state, entry),
    }

