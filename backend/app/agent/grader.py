from pydantic import BaseModel, Field

from app.agent.state import AgentState, append_trace
from app.core.llm import chat
from app.core.prompts import GRADER_PROMPT


class GradeDecision(BaseModel):
    sufficient: bool = Field(
        description="True if the note excerpts contain enough information to answer the question"
    )
    reason: str = Field(description="One short sentence explaining the verdict")


def grade_node(state: AgentState) -> dict:
    question = state["question"]
    documents = state.get("documents", [])

    if not documents:
        return {
            "context_sufficient": False,
            "trace": append_trace(
                state,
                {
                    "step": "grade",
                    "decision": "insufficient",
                    "reason": "no notes retrieved from knowledge base",
                },
            ),
        }

    context = "\n\n---\n\n".join(
        f"[{doc['metadata'].get('filename', 'notes')}, Page "
        f"{doc['metadata'].get('page_number', 1)}, Chunk "
        f"{doc['metadata'].get('chunk_index', 0)}]\n{doc['text']}"
        for doc in documents
    )

    try:
        decision = chat(
            [
                ("system", GRADER_PROMPT),
                ("human", f"Question:\n{question}\n\nNote excerpts:\n{context}"),
            ],
            schema=GradeDecision,
        )
    except Exception as exc:  # noqa: BLE001 - degrade gracefully, never crash the graph
        # Grader model outage: proceed with the retrieved notes so the
        # synthesizer can still attempt a strictly-grounded answer. The
        # synthesizer's own prompt plus the grounding guard keep the output
        # honest even when sufficiency could not be judged.
        return {
            "context_sufficient": True,
            "trace": append_trace(
                state,
                {
                    "step": "grade",
                    "decision": "sufficient",
                    "reason": f"Grader model unavailable ({exc}); proceeding with retrieved notes to attempt a grounded answer.",
                },
            ),
        }

    return {
        "context_sufficient": decision.sufficient,
        "trace": append_trace(
            state,
            {
                "step": "grade",
                "decision": "sufficient" if decision.sufficient else "insufficient",
                "reason": decision.reason,
            },
        ),
    }

