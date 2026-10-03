from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage

from app.agent.state import AgentState, append_trace
from app.agent.synthesize import build_context
from app.core.llm import chat
from app.core.prompts import GROUNDING_CHECK_PROMPT


class GroundingDecision(BaseModel):
    grounded: bool = Field(
        description="True if all claims in the answer are strictly supported by the context"
    )
    reason: str = Field(
        description="One short sentence explaining why it is grounded or identifying unsupported claims"
    )
    corrected_answer: str | None = Field(
        default=None,
        description=(
            "If not grounded, the corrected answer: the candidate answer with "
            "unsupported claims removed or fixed. Preserve the answer's intent "
            "and any refusal; never add new content."
        ),
    )


_REFUSAL_MARKERS = (
    "do not contain",
    "does not contain",
    "doesn't contain",
    "don't contain",
    "no information",
    "not contain",
    "not mentioned",
    "not provided",
    "not specified",
    "not found in",
    "cannot find",
)


def looks_like_refusal(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in _REFUSAL_MARKERS)


def grounding_check_node(state: AgentState) -> dict:
    """Verifies that the synthesized answer is factually grounded in the retrieved context.

    This node is the last step before END and is the single authority for
    persisting the final assistant message: exactly one AIMessage per turn is
    appended to the conversation history, containing the corrected answer when
    a correction was produced. This prevents both the original (potentially
    hallucinated) answer and its correction from co-existing in memory.

    Verdicts:
    - "verified":   every claim is supported by the retrieved context.
    - "corrected":  ungrounded claims were removed/rewritten by the guard.
    - "unverified": ungrounded claims were detected but no correction was
                    available, or the check itself failed; the answer is
                    returned as-is and explicitly flagged, never silently
                    labeled as verified.
    - "skipped":    direct conversational turn with no retrieved context.
    """
    answer = state.get("answer", "")
    route = state.get("route", "")
    context = build_context(state)

    # For direct chit-chat/greetings without context, skip grounding check
    if route == "direct" or not context:
        return {
            "answer": answer,
            "grounding_verdict": "skipped",
            "messages": [AIMessage(content=answer)],
            "trace": append_trace(
                state,
                {
                    "step": "grounding",
                    "status": "skipped",
                    "detail": "Direct conversational response; context verification skipped.",
                },
            ),
        }

    try:
        decision: GroundingDecision = chat(
            [
                ("system", GROUNDING_CHECK_PROMPT),
                (
                    "human",
                    f"Retrieved Context:\n{context}\n\nCandidate Answer to Verify:\n{answer}",
                ),
            ],
            schema=GroundingDecision,
        )

        if decision.grounded:
            verdict = "verified"
            final_answer = answer
            detail = f"Factually grounded: {decision.reason}"
        elif decision.corrected_answer and decision.corrected_answer.strip():
            corrected = decision.corrected_answer.strip()
            if looks_like_refusal(answer) and not looks_like_refusal(corrected):
                # Deterministic safety net: the guard tried to replace an
                # honest refusal with brand-new content. That flips the
                # answer's intent, so the correction is rejected and the
                # honest refusal is kept, flagged as unverified.
                verdict = "unverified"
                final_answer = answer
                detail = (
                    "Correction rejected: it would have replaced an honest "
                    "refusal with new content; original refusal kept. "
                    f"Guard reason: {decision.reason}"
                )
            else:
                verdict = "corrected"
                final_answer = corrected
                detail = f"Hallucination guard adjusted answer: {decision.reason}"
        else:
            # Ungrounded claims detected, but the guard produced no corrected
            # version. Never claim "corrected" without an actual correction.
            verdict = "unverified"
            final_answer = answer
            detail = (
                "Ungrounded claims detected but no corrected answer was provided; "
                f"answer returned with an explicit warning: {decision.reason}"
            )

    except Exception as exc:  # noqa: BLE001 - graceful fallback, never crash the graph
        verdict = "unverified"
        final_answer = answer
        detail = f"Grounding check skipped due to error: {exc}"

    return {
        "answer": final_answer,
        "grounding_verdict": verdict,
        "messages": [AIMessage(content=final_answer)],
        "trace": append_trace(
            state,
            {
                "step": "grounding",
                "status": verdict,
                "detail": detail,
            },
        ),
    }
