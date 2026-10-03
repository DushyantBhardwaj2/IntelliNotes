# IntelliNotes — Implementation Walkthrough & Verification

We completed an in-depth audit, bug fixing, anti-hallucination guardrail implementation, document-scoped retrieval, automated test suite creation, and UI modernization for **IntelliNotes**.

> **Round 2 (independent re-audit & hardening) is documented at the bottom of
> this file** — it fixed 6 additional bugs found by re-auditing the round-1
> work, including a conversation-memory pollution bug and a guard-induced
> "pivot" behavior discovered during live end-to-end testing.

---

## Problems Identified & Solutions Implemented

### 1. Zero-Hallucination Guard & Anti-Hallucination Pipeline
- **Problem**: Previously, `SYNTHESIZER_PROMPT` Rule 5 instructed the model to answer from parametric "general knowledge" when document context was missing, resulting in fabricated facts about private documents. Furthermore, there was no post-synthesis verification.
- **Solution**:
  1. Updated `backend/app/core/prompts.py` with strict grounding rules: If context does not contain the answer, the model explicitly states it without guessing.
  2. Built `backend/app/agent/grounding.py`: An autonomous **Self-RAG Anti-Hallucination Guard** node in the LangGraph pipeline. It cross-checks candidate answers against context chunks and auto-corrects any unsupported claims before outputting to the user.
  3. Added the grounding step into the live agent trace for transparency.

### 2. Document Scoping & Cross-Document Isolation
- **Problem**: Queries previously searched across all documents in ChromaDB indiscriminately. Uploading multiple documents polluted retrieval contexts.
- **Solution**:
  1. Updated `backend/app/ingestion/vectorstore.py` to support `doc_id` metadata filtering in `search_notes(query, doc_id=...)`.
  2. Added document deletion (`delete_document(doc_id)`) and full reset (`clear_all()`).
  3. Added `doc_id` to `backend/app/schemas.py` `ChatRequest` and exposed `DELETE /documents/{doc_id}` in `backend/app/main.py`.
  4. Added a Document Selector dropdown and document manager in the Streamlit frontend.

### 3. Page-Level Ingestion & Exact Citations
- **Problem**: PDF extraction collapsed all pages into a flat string, discarding page boundaries. Citations only showed arbitrary chunk numbers (`chunk 3`).
- **Solution**:
  1. Rewrote `backend/app/ingestion/loader.py` with `extract_pdf_pages()` to extract text page-by-page.
  2. Updated chunking to preserve `page_number` in `Chunk.metadata`.
  3. Updated `backend/app/agent/synthesize.py` and the UI to cite exact document pages: `[Document: filename, Page: X]`.

### 4. Multi-Turn Routing & Context Condensation
- **Problem**: `backend/app/agent/router.py` evaluated only the raw latest query without prior conversation history. Follow-ups were frequently misrouted.
- **Solution**:
  1. Updated `decide_route()` to incorporate recent dialogue history into intent classification.
  2. Enhanced `condense_question()` in `backend/app/agent/retriever.py` to strip LLM conversational filler and resolve ambiguous pronouns before vector retrieval.
  3. Added empty-store detection: routes to web fallback or alerts user if no documents exist in the knowledge base.

### 5. Automated Test Suite
- **Problem**: The project had 0 tests.
- **Solution**: Created a 24-test suite across 4 test modules:
  - `backend/tests/test_loader.py` (6 tests: text cleaning, chunking boundaries, page tracking, corrupt/empty PDF handling)
  - `backend/tests/test_vectorstore.py` (3 tests: ingestion, scoped search, document deletion & listing)
  - `backend/tests/test_agent.py` (8 tests: routing, sufficiency grading, Self-RAG grounding, graph structure)
  - `backend/tests/test_api.py` (7 tests: FastAPI endpoints `/health`, `/documents`, `/upload-document/`, `/chat/`, `DELETE /documents/{doc_id}`)

### 6. Modernized Frontend UI & Observability
- **Solution**: Completely overhauled `frontend/app.py` with a dark theme, visual DAG trace cards, document management (with delete buttons), document scope selector, and quick-start prompt chips.

---

## Test Suite Execution Results

Executed:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "& .venv\Scripts\python.exe -m pytest backend/tests -v"
```

```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1
rootdir: C:\Users\Dushy\OneDrive\Desktop\Projects\IntelliNotes
collected 24 items

backend/tests/test_agent.py::test_router_node_notes_path PASSED          [  4%]
backend/tests/test_agent.py::test_router_node_empty_store_fallback PASSED [  8%]
backend/tests/test_agent.py::test_grade_node_no_documents PASSED         [ 12%]
backend/tests/test_agent.py::test_grade_node_with_documents PASSED       [ 16%]
backend/tests/test_agent.py::test_grounding_check_node_skipped_on_direct PASSED [ 20%]
backend/tests/test_agent.py::test_grounding_check_node_verified PASSED   [ 25%]
backend/tests/test_agent.py::test_grounding_check_node_corrected PASSED  [ 29%]
backend/tests/test_agent.py::test_build_graph_structure PASSED           [ 33%]
backend/tests/test_api.py::test_root_endpoint PASSED                     [ 37%]
backend/tests/test_api.py::test_health_endpoint PASSED                   [ 41%]
backend/tests/test_api.py::test_upload_non_pdf_rejected PASSED           [ 45%]
backend/tests/test_api.py::test_upload_pdf_success PASSED                [ 50%]
backend/tests/test_api.py::test_chat_endpoint_success PASSED             [ 54%]
backend/tests/test_api.py::test_delete_document PASSED                   [ 58%]
backend/tests/test_api.py::test_clear_all_documents PASSED              [ 62%]
backend/tests/test_loader.py::test_clean_text PASSED                     [ 66%]
backend/tests/test_loader.py::test_chunk_text_basic PASSED              [ 70%]
backend/tests/test_loader.py::test_chunk_text_short PASSED              [ 75%]
backend/tests/test_loader.py::test_extract_pdf_pages PASSED              [ 79%]
backend/tests/test_loader.py::test_load_pdf_chunks_success PASSED        [ 83%]
backend/tests/test_loader.py::test_load_pdf_chunks_empty_raises_error PASSED [ 87%]
backend/tests/test_vectorstore.py::test_add_and_count_chunks PASSED      [ 91%]
backend/tests/test_vectorstore.py::test_search_notes_and_scoping PASSED  [ 95%]
backend/tests/test_vectorstore.py::test_list_and_delete_document PASSED [100%]

======================== 24 passed in 7.78s ========================
```

---

## How to Run Locally

### 1. Run the FastAPI Backend
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "& .venv\Scripts\uvicorn.exe app.main:app --app-dir backend --reload --port 8000"
```
Interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Run the Streamlit UI
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "& .venv\Scripts\streamlit.exe run frontend/app.py"
```
Browser UI: [http://localhost:8501](http://localhost:8501)

### 3. Run the Test Suite
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "& .venv\Scripts\python.exe -m pytest backend/tests -v"
```

### 4. Verify API Keys & Models
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "& .venv\Scripts\python.exe scripts\verify_setup.py"
```

### 5. Live End-to-End Smoke Test (needs running backend)
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "& .venv\Scripts\python.exe scripts\smoke_test.py"
```

---

# Round 2 — Independent Re-Audit & Hardening

A second, independent audit of the round-1 implementation found 6 additional
bugs (plus several nits). All were fixed, unit-tested, and verified against the
**live** Gemini + Tavily services, not just mocks.

## Bugs Found & Fixed

### 1. [HIGH] Grounding correction polluted conversation memory
- **Bug**: `synthesize_node` appended its (potentially hallucinated) answer to
  the message history, and `grounding_check_node` appended a *second* corrected
  `AIMessage` on top. Multi-turn conversations therefore kept **both** the
  hallucinated and the corrected answer in memory, so follow-up turns still
  saw the hallucinated text.
- **Fix**: The grounding node is now the *single authority* for persisting the
  final assistant message. `synthesize_node` no longer touches `messages`;
  `grounding_check_node` appends exactly one `AIMessage` per turn (corrected or
  not). Verified live via the SQLite checkpointer: 2 turns → exactly
  `[human, ai, human, ai]`.
- **Regression test**: `test_grounding_correction_replaces_history_not_appends`.

### 2. [HIGH] Guard-induced "pivot" (found by live testing, two layers deep)
- **Bug**: When the grader judged retrieved notes insufficient (and web search
  was off), the final answer was a summary of unrelated document content
  instead of an honest refusal. Layer-by-layer isolation proved the
  **grounding guard itself** was flipping the synthesizer's honest refusal
  ("the documents do not contain this information") into a context summary,
  because its prompt equated "grounded" with "reflects the context".
- **Fix** (three layers):
  1. `SYNTHESIZER_PROMPT` + an `INSUFFICIENT_CONTEXT_NOTE` appended when the
     grader already flagged insufficiency and no web results exist — the model
     must refuse instead of pivoting (`synthesize.py`).
  2. `GROUNDING_CHECK_PROMPT` now explicitly rules: honest refusals are
     grounded; support is judged relative to the question; corrections must
     preserve intent and never add content.
  3. A **deterministic safety net** (`looks_like_refusal`): if a "correction"
     would strip a refusal and replace it with new content, the correction is
     rejected, the refusal kept, and the turn flagged `unverified`.
- **Live evidence**: scenario 3 ("CEO bonus", absent) and scenario 4 (scoped to
  the wrong document) both now return
  *"The provided document(s) do not contain information to answer this
  question."* with zero cross-document leakage.

### 3. [MEDIUM] Dishonest `grounding_verdict` defaults
- **Bug**: API schema and endpoint defaulted missing verdicts to `"verified"`,
  and the guard labeled uncorrected answers `"corrected"`.
- **Fix**: defaults are now `null` / `"unverified"`; `"corrected"` is only
  emitted when a real correction was applied. Frontend gained an amber
  `UNVERIFIED` badge.

### 4. [MEDIUM] Sparse-PDF upload crashed with HTTP 500
- **Bug**: a PDF with ≥30 characters but <5 words produced zero chunks →
  `chunks[0]` IndexError → 500.
- **Fix**: `load_pdf_chunks` raises a clean `ValueError` ("too short or
  sparse"), the endpoint returns 400, and a defensive guard remains.

### 5. [MEDIUM] No graceful degradation for LLM outages
- **Bug**: a transient Gemini failure in the router or grader nodes failed the
  whole conversation with 503 (both nodes had no error handling).
- **Fix**: `decide_route` falls back to a deterministic keyword heuristic
  (`heuristic_route`), and `grade_node` degrades to "sufficient" with an honest
  trace note. Both fallbacks are traced for transparency.

### 6. [NIT] Hardening & polish
- Upload size limit (default 20 MB → HTTP 413, configurable via
  `MAX_UPLOAD_MB`).
- README accuracy: default model is `gemini-3.5-flash-lite` (badges/text
  updated); test counts updated.
- Frontend: removed dead `prompt` variable, delete/clear buttons now surface
  errors, honest verdict default.
- Thread-safety of the SQLite checkpointer was **re-verified against the
  installed LangGraph source**: `SqliteSaver` serializes all operations behind
  an internal `threading.Lock` and enables WAL, so single-process use is safe
  (multi-worker deployments would need `PostgresSaver` — documented in
  `graph.py`).

## Round 2 Verification

- Unit/integration suite: **50 passed** (24 original + 26 new, all mocked, no
  API cost).
- Live smoke test (`scripts/smoke_test.py`): **18/18 checks passed** against
  the real backend, real Gemini + Tavily, real generated PDFs:
  - page-aware upload (3 chunks / 1 chunk),
  - grounded Q&A with `[Document: …, Page: N]` citations and `verified`
    verdicts,
  - multi-turn pronoun resolution ("What is its retry limit?" →
    "Atlas Protocol retry limit"),
  - honest refusal for absent information (no fabricated bonus),
  - scoped isolation (asking atlas questions against the finance doc leaks
    nothing and refuses),
  - memory integrity (exactly one AI message per turn, final answer persisted),
  - cleanup (test documents removed, pre-existing store untouched).

