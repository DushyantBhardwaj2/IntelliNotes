# In-Depth Code Review, Bug Fixes & Zero-Hallucination Agentic RAG Plan

## Executive Summary

We conducted an in-depth review of the **IntelliNotes** codebase (FastAPI backend + LangGraph multi-step agent + ChromaDB vectorstore + Gemini 3.5 Flash / Embeddings + Tavily search + Streamlit frontend).

The core setup (Gemini API, embeddings, Tavily) was verified and confirmed working. However, an in-depth code audit identified several **critical bugs, hallucination risks, data leakage flaws, and missing engineering standards** that must be resolved to make this a truly elite, resume-worthy project.

---

## Codebase Audit & Bugs Identified

### 1. [CRITICAL] Hallucination Encouragement in Synthesizer Prompt
- **Issue**: In `backend/app/core/prompts.py`, Rule 5 explicitly stated:
  `"5. If there is no relevant context at all, say so honestly, then answer briefly from your general knowledge while making clear it did not come from the user's notes or a web search."`
- **Impact**: If a user uploads a specific document (e.g., an employment contract, financial statement, or syllabus) and asks a question not answered in the text, the model is prompted to synthesize from general knowledge. This directly causes ungrounded assertions and hallucinations.
- **Fix**: Update Rule 5 to enforce strict grounding: If the retrieved excerpts do not contain the answer (and web search is disabled or yields no results), the agent must strictly state that the document does not contain the information, without guessing or hallucinating facts.

### 2. [CRITICAL] Lack of Document Scoping & Cross-Document Pollution
- **Issue**: In `backend/app/ingestion/vectorstore.py`, `search_notes(query)` calls `similarity_search(query)` without any metadata filtering.
- **Impact**: If a user uploads multiple PDFs over time (e.g. `Biology_Notes.pdf` and `Tax_Law.pdf`), queries search across *all* documents simultaneously. Chunks from completely unrelated documents can contaminate the prompt context and confuse the LLM.
- **Fix**:
  - Add optional `doc_id: str | None = None` filtering in `search_notes(query, doc_id=...)` using Chroma metadata filters `{"doc_id": doc_id}`.
  - Update `ChatRequest` schema in `backend/app/schemas.py` to accept an optional `doc_id`.
  - Add a document selector dropdown in the Streamlit UI (chat with "All Documents" or a specific uploaded document).
  - Add delete document functionality (`DELETE /documents/{doc_id}`) so users can remove old or test documents.

### 3. [HIGH] Loss of Page-Level Metadata in PDF Ingestion
- **Issue**: In `backend/app/ingestion/loader.py`, `extract_pdf_text` joins all pages into a single flat string. Chunking then splits the flat string without tracking which page each chunk came from.
- **Impact**: Citations in answers and agent traces only say `(chunk 3)` or `(from notes.pdf)`. Real production systems cite exact page numbers (e.g. `[notes.pdf, Page 4]`), which is a major resume differentiator.
- **Fix**: Extract text page by page, track page boundaries during chunking, and store `page_number` in the chunk metadata.

### 4. [HIGH] Multi-Turn Router Context Blindness
- **Issue**: In `backend/app/agent/router.py`, `decide_route(question)` evaluates only `state["question"]` without any chat history.
- **Impact**: In multi-turn conversations, if a user asks a follow-up like "Explain section 2 in more detail", the router sees only "Explain section 2 in more detail", potentially misclassifying it as "direct" or "web" because it lacks the context that the conversation is about an uploaded PDF.
- **Fix**: Pass recent conversation history into the router decision so follow-up references to prior context are properly routed to `notes`.

### 5. [HIGH] Empty Knowledge Base Edge Case
- **Issue**: If a user asks a question before uploading any documents, the router classifies it as `notes`, retrieval returns `[]`, grader flags `insufficient`, and the system automatically falls back to Tavily web search. The user gets answers from random public websites rather than being informed that no documents have been uploaded yet.
- **Fix**: Detect when the vectorstore has 0 chunks for the requested scope and either route to web with an explicit notification or inform the user to upload a document first.

### 6. [HIGH] Missing Hallucination / Grounding Verification Node (Self-RAG)
- **Issue**: Currently, after `synthesize_node` runs, the answer is immediately returned to the user without verifying whether the answer made up claims not present in the retrieved chunks.
- **Fix**: Add a **Grounding Verifier** step in the agent workflow (Self-RAG pattern). It checks whether the generated response is strictly supported by the context. If grounded, it passes; if unsupported claims are found, it flags and refines the answer. This is an industry standard for zero-hallucination agentic systems.

### 7. [MEDIUM] Repeated ChromaDB Instantiation
- **Issue**: In `backend/app/ingestion/vectorstore.py`, `get_vectorstore()` creates a new `Chroma(...)` object on every single operation.
- **Fix**: Cache the Chroma instance or use a singleton client with a thread lock to prevent file lock issues on Windows.

### 8. [MEDIUM] Zero Automated Tests
- **Issue**: `backend/tests/` contains only `__init__.py`.
- **Fix**: Build a comprehensive pytest suite covering PDF loading, chunking with page tracking, vector store CRUD, routing logic, grading logic, grounding verification, and FastAPI endpoints.

### 9. [MEDIUM] Frontend UI & User Experience Polish
- **Issue**: Streamlit frontend is barebones, lacking visual distinction, timeline trace formatting, document deletion, and prompt suggestion chips.
- **Fix**: Modernize the UI with clean dark-mode styling, an interactive agent trace with step badges, a document manager (list + delete), and instant prompt chips.

---

## Proposed Changes

### Backend Core & Prompts

#### [MODIFY] `backend/app/core/prompts.py`
- Update `SYNTHESIZER_PROMPT` to enforce zero hallucination and page-level citation formatting.
- Add `GROUNDING_CHECK_PROMPT` to verify synthesized responses against context.
- Update `ROUTER_PROMPT` to handle conversational context and empty-store awareness.

#### [MODIFY] `backend/app/ingestion/loader.py`
- Modify `extract_pdf_text` to preserve page numbers.
- Update `chunk_text` to associate each chunk with its originating `page_number` (1-indexed).
- Store `page_number` in `Chunk.metadata`.

#### [MODIFY] `backend/app/ingestion/vectorstore.py`
- Add singleton pattern for `get_vectorstore()`.
- Support `doc_id` filtering in `search_notes(query, doc_id=None, k=None)`.
- Add `delete_document(doc_id: str)` to allow removing uploaded PDFs.
- Add `clear_all()` for full index reset.

### Backend Agent & Graph

#### [NEW] `backend/app/agent/grounding.py`
- Implement `grounding_check_node(state: AgentState)` that validates the synthesized answer against the retrieved chunks and adds a `"grounding"` step to the agent trace.

#### [MODIFY] `backend/app/agent/router.py`
- Pass conversation context to route decisions to handle follow-up queries.
- Accept optional `doc_id` in state.

#### [MODIFY] `backend/app/agent/retriever.py`
- Pass `doc_id` to `vectorstore.search_notes`.
- Include `page_number` in trace source details.

#### [MODIFY] `backend/app/agent/synthesize.py`
- Build context with page numbers: `[Document: filename, Page: X, Chunk: Y]`.
- Strict citation rules.

#### [MODIFY] `backend/app/agent/state.py`
- Add `doc_id: str | None` and `grounding_verdict: str` to `AgentState`.

#### [MODIFY] `backend/app/agent/graph.py`
- Connect `synthesize -> grounding_check -> END`.

### Backend API & Schemas

#### [MODIFY] `backend/app/schemas.py`
- Add `doc_id: str | None = None` to `ChatRequest`.
- Add `DeleteResponse` schema.

#### [MODIFY] `backend/app/main.py`
- Pass `doc_id` to graph state in `chat` endpoint.
- Add `DELETE /documents/{doc_id}` endpoint.
- Add `DELETE /documents/` endpoint (clear all).

### Frontend

#### [MODIFY] `frontend/app.py`
- Modernized UI with custom CSS styling and badges.
- Document selector dropdown: "All Documents" or specific PDF.
- Document management: view indexed documents, chunk counts, and delete button per document.
- Beautiful, structured visual Agent Trace showing step-by-step progress:
  - 🧭 Router Decision
  - 📚 Retrieval (with filename and exact page numbers)
  - ⚖️ Grader Sufficiency Verdict
  - 🌐 Web Search (if triggered)
  - 🛡️ Grounding / Anti-Hallucination Verification
  - ✍️ Final Answer Synthesis
- Quick prompt suggestion chips for first-time users.

### Automated Test Suite

#### [NEW] `backend/tests/test_loader.py`
- Tests PDF text extraction, page tracking, text cleaning, chunk boundary splitting, empty/corrupted PDF rejection.

#### [NEW] `backend/tests/test_vectorstore.py`
- Tests chunk ingestion, similarity search, `doc_id` filtering, document listing, single-document deletion, and full index reset.

#### [NEW] `backend/tests/test_agent.py`
- Unit tests for router logic, retriever with condensing, grader sufficiency, and grounding check.

#### [NEW] `backend/tests/test_api.py`
- End-to-end FastAPI endpoint tests using `TestClient`:
  - `GET /health`
  - `GET /documents`
  - `POST /upload-document/`
  - `POST /chat/` (mocked LLM for fast test execution)
  - `DELETE /documents/{doc_id}`

---

## Verification Plan

### Automated Tests
Run full pytest suite in virtual environment:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "& .venv\Scripts\python.exe -m pytest backend/tests -v"
```

### Manual Verification
1. Run backend server:
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -Command "& .venv\Scripts\uvicorn.exe app.main:app --app-dir backend --port 8000"
   ```
2. Upload a sample multi-page PDF document via the API/Streamlit frontend.
3. Verify chunking captures page numbers accurately.
4. Test Query 1 (Direct document query): Verify it routes to `notes`, retrieves chunks with page numbers, grader passes, grounding check passes, returns accurate answer with zero hallucination.
5. Test Query 2 (Document query with missing detail): Verify it routes to `notes`, retrieves chunks, grader identifies insufficiency, triggers Tavily web search (or if web search is toggled off, cleanly states that the document does not contain this information without hallucinating).
6. Test Query 3 (Follow-up multi-turn query): Verify condensation rewrites the query accurately preserving context.
7. Test Document Scoping: Upload two distinct documents, select one in the document filter, and verify retrieval only pulls from the chosen document.
8. Test Document Deletion: Delete a document and verify it is removed from the vectorstore and UI.

---

# Round 2 — Re-Audit Findings & Fixes (executed)

An independent re-audit of the implemented system identified 6 additional
bugs. All were fixed, unit-tested (50 tests total), and verified live.

| # | Severity | Finding | Resolution |
|---|----------|---------|------------|
| 1 | HIGH | Grounding correction *appended* a second AIMessage, leaving both the hallucinated and corrected answers in multi-turn memory | Grounding node is now the sole authority for the final assistant message: exactly one `AIMessage` per turn |
| 2 | HIGH | Guard-induced pivot: the grounding guard rewrote honest refusals into context summaries when the grader marked notes insufficient | Three-layer fix: anti-pivot synthesizer instruction + grounding-prompt refusal rules + deterministic `looks_like_refusal` net rejecting intent-flipping corrections |
| 3 | MEDIUM | Missing verdicts defaulted to `"verified"`; uncorrected answers labeled `"corrected"` | Defaults are `null`/`"unverified"`; `"corrected"` only with a real correction; frontend amber UNVERIFIED badge |
| 4 | MEDIUM | Sparse PDFs (≥30 chars, <5 words) crashed uploads with HTTP 500 | Loader raises clean `ValueError`; endpoint returns 400 |
| 5 | MEDIUM | Router/grader LLM outages failed the whole conversation (503) | Deterministic keyword routing fallback + safe grading default, both traced honestly |
| 6 | NIT | No upload size limit; README model-name inaccuracies; dead frontend code; delete buttons silent on failure | 20 MB limit (HTTP 413, `MAX_UPLOAD_MB`); docs corrected; dead code removed; error feedback added |

Thread-safety of the SQLite checkpointer was re-checked against the installed
LangGraph source and confirmed safe for single-process use (internal
`threading.Lock` + WAL); multi-worker guidance documented in `graph.py`.

Verification: 50/50 pytest (mocked, no API cost) and 18/18 live smoke checks
(`scripts/smoke_test.py`) against real Gemini + Tavily with generated PDFs.
