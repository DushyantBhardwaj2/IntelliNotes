from langchain_core.messages import SystemMessage

from app.agent.state import AgentState, append_trace
from app.core.llm import chat, to_text
from app.core.prompts import SYNTHESIZER_PROMPT

NO_CONTEXT = "(No note excerpts or web results were retrieved for this question.)"

INSUFFICIENT_CONTEXT_NOTE = (
    "\n\nIMPORTANT: The retrieved context above was already judged INSUFFICIENT to "
    "answer the user's question, and no web results are available. Begin your answer "
    "by stating clearly that the provided document(s) do not contain the requested "
    "information. Do NOT substitute an unrelated summary of other document content; "
    "only reference document facts if they directly help explain what is missing."
)


def build_context(state: AgentState) -> str:
    parts: list[str] = []

    for doc in state.get("documents", []):
        metadata = doc.get("metadata", {})
        filename = metadata.get("filename", "notes.pdf")
        page = metadata.get("page_number", 1)
        chunk = metadata.get("chunk_index", 0)
        parts.append(
            f"### Note excerpt — Document: {filename} (Page {page}, Chunk {chunk})\n{doc['text']}"
        )

    for result in state.get("web_results", []):
        parts.append(
            f"### Web result — {result['title']} ({result['url']})\n{result['content']}"
        )

    return "\n\n".join(parts)


def synthesize_node(state: AgentState) -> dict:
    context = build_context(state)
    prompt = SYNTHESIZER_PROMPT.format(context=context if context else NO_CONTEXT)

    # The grader already flagged the retrieved notes as insufficient and web
    # fallback did not (or could not) rescue the turn: instruct the model to
    # refuse explicitly instead of pivoting to an unrelated document summary.
    if context and not state.get("context_sufficient", True) and not state.get(
        "web_results"
    ):
        prompt += INSUFFICIENT_CONTEXT_NOTE

    system = SystemMessage(content=prompt)

    answer = to_text(chat([system] + list(state.get("messages", [])))).strip()

    used_notes = len(state.get("documents", []))
    used_web = len(state.get("web_results", []))

    # Note: the final AIMessage is persisted by grounding_check_node (the last
    # node before END), so a grounding correction replaces the answer instead
    # of appending a second, contradictory assistant message to the history.
    return {
        "answer": answer,
        "trace": append_trace(
            state,
            {
                "step": "synthesize",
                "detail": f"answered using {used_notes} note chunk(s) "
                f"and {used_web} web result(s)",
            },
        ),
    }

