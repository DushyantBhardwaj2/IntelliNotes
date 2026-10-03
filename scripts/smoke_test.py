"""Live end-to-end smoke test for IntelliNotes.

Requires a running backend (uvicorn app.main:app --app-dir backend --port 8000)
and valid API keys in .env. Exercises the full agentic pipeline with the real
Gemini + Tavily services: upload, page-aware retrieval, multi-turn condensation,
anti-hallucination refusals, document scoping, memory integrity, and cleanup.

Run:  python scripts/smoke_test.py
"""

import sys
import time
import uuid
from pathlib import Path

import requests

API = "http://localhost:8000"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

PASSED = []
FAILED = []


def check(name, condition, evidence=""):
    if condition:
        PASSED.append(name)
        print(f"  [PASS] {name}")
    else:
        FAILED.append(name)
        print(f"  [FAIL] {name}  {evidence}")


def make_pdf(page_texts):
    """Build a minimal valid PDF with one text object per page."""
    objects = {}
    n = len(page_texts)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n))
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode()
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    for i, text in enumerate(page_texts):
        escaped = (
            text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        )
        stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode()
        objects[4 + 2 * i] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {5 + 2 * i} 0 R /Resources << /Font << /F1 3 0 R >> >> >>"
        ).encode()
        objects[5 + 2 * i] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode()
            + stream
            + b"\nendstream"
        )
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objects[num] + b"\nendobj\n"
    xref_pos = len(out)
    max_obj = max(objects)
    out += f"xref\n0 {max_obj + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, max_obj + 1):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {max_obj + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF"
    ).encode()
    return bytes(out)


ATLAS_PAGES = [
    "The Atlas Protocol is a corporate messaging standard used by field engineers. "
    "The Atlas Protocol listening service operates on port 5050, and the current "
    "release is version 2.4. Every connection begins with a three phase handshake.",
    "Transmission reliability rules: the retry limit is 5 attempts per message, "
    "after which the sender receives a permanent failure notice. The default "
    "timeout is 30 seconds per attempt. Failed messages are logged locally for seven days.",
    "Security requirements: all payloads must be encrypted with AES-256 before "
    "transmission. Encryption keys rotate automatically on a weekly schedule. "
    "Compliance audits happen quarterly.",
]
MERIDIAN_PAGES = [
    "Meridian Finance internal report for the third quarter. Total revenue was "
    "4.2 million dollars. Operating costs were 1.1 million dollars. Net income "
    "was therefore 3.1 million dollars. The board meets in November.",
]

REFUSAL_PHRASES = (
    "not contain",
    "does not",
    "doesn't",
    "no information",
    "not mentioned",
    "not provide",
    "not specified",
    "not found",
    "cannot find",
)


def wait_for_health():
    for _ in range(60):
        try:
            r = requests.get(f"{API}/health", timeout=5)
            if r.status_code == 200:
                print("Server healthy:", r.json())
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


def chat(session_id, message, web_enabled, doc_id=None):
    payload = {
        "session_id": session_id,
        "message": message,
        "web_enabled": web_enabled,
    }
    if doc_id:
        payload["doc_id"] = doc_id
    r = requests.post(f"{API}/chat/", json=payload, timeout=300)
    r.raise_for_status()
    return r.json()


def trace_summary(trace):
    steps = []
    for t in trace:
        if t.get("step") == "router":
            steps.append(f"router:{t.get('decision')}")
        elif t.get("step") == "grade":
            steps.append(f"grade:{t.get('decision')}")
        elif t.get("step") == "grounding":
            steps.append(f"grounding:{t.get('status')}")
        else:
            steps.append(t.get("step", "?"))
    return " -> ".join(steps)


def is_refusal(answer):
    low = answer.lower()
    return any(phrase in low for phrase in REFUSAL_PHRASES)


def main():
    if not wait_for_health():
        print("FATAL: server never became healthy")
        sys.exit(1)

    pre_docs = requests.get(f"{API}/documents", timeout=30).json()
    pre_ids = {d["doc_id"] for d in pre_docs}
    print(f"\nPre-existing documents: {[d['filename'] for d in pre_docs]}")

    atlas_pdf = make_pdf(ATLAS_PAGES)
    r = requests.post(
        f"{API}/upload-document/",
        files={"file": ("atlas-protocol-guide.pdf", atlas_pdf, "application/pdf")},
        timeout=120,
    )
    r.raise_for_status()
    atlas = r.json()

    meridian_pdf = make_pdf(MERIDIAN_PAGES)
    r = requests.post(
        f"{API}/upload-document/",
        files={"file": ("meridian-finance.pdf", meridian_pdf, "application/pdf")},
        timeout=120,
    )
    r.raise_for_status()
    meridian = r.json()

    check(
        "upload atlas -> 3 chunks (page-aware)",
        atlas["processed_chunks"] == 3,
        f"got {atlas['processed_chunks']}",
    )
    check(
        "upload meridian -> 1 chunk",
        meridian["processed_chunks"] == 1,
        f"got {meridian['processed_chunks']}",
    )

    print("\n--- Scenario 1: notes query scoped to atlas (web off) ---")
    sid_a = uuid.uuid4().hex
    s1 = chat(
        sid_a,
        "What port does the Atlas Protocol use and what version is the current release?",
        web_enabled=False,
        doc_id=atlas["doc_id"],
    )
    print("trace:", trace_summary(s1["trace"]))
    print("answer:", s1["answer"][:300])
    check("s1 routes to notes", "router:notes" in trace_summary(s1["trace"]))
    check("s1 answer contains port 5050", "5050" in s1["answer"])
    check("s1 answer contains version 2.4", "2.4" in s1["answer"])
    check(
        "s1 grounding verdict is honest",
        s1["grounding_verdict"] in ("verified", "corrected", "unverified"),
        f"got {s1['grounding_verdict']}",
    )
    retrieve = next(t for t in s1["trace"] if t.get("step") == "retrieve")
    pages = {src.get("page") for src in retrieve.get("sources", [])}
    check("s1 citations carry page numbers", 1 in pages, f"pages={pages}")

    print("\n--- Scenario 2: follow-up 'What is its retry limit?' (same session) ---")
    s2 = chat(
        sid_a,
        "What is its retry limit?",
        web_enabled=False,
        doc_id=atlas["doc_id"],
    )
    print("trace:", trace_summary(s2["trace"]))
    retrieve2 = next(t for t in s2["trace"] if t.get("step") == "retrieve")
    print("condensed query:", retrieve2.get("question_used"))
    print("answer:", s2["answer"][:300])
    check("s2 routes to notes", "router:notes" in trace_summary(s2["trace"]))
    check(
        "s2 answer states retry limit 5",
        "5" in s2["answer"] or "five" in s2["answer"].lower(),
    )
    check(
        "s2 condensation resolved the pronoun",
        "atlas" in retrieve2.get("question_used", "").lower(),
        f"used: {retrieve2.get('question_used')}",
    )

    print("\n--- Scenario 3: ask for absent info (CEO bonus), web off ---")
    sid_c = uuid.uuid4().hex
    s3 = chat(
        sid_c,
        "What does the guide say about the CEO's annual bonus?",
        web_enabled=False,
        doc_id=atlas["doc_id"],
    )
    print("trace:", trace_summary(s3["trace"]))
    print("answer:", s3["answer"][:300])
    check("s3 refuses honestly (no fabricated bonus)", is_refusal(s3["answer"]))
    check(
        "s3 verdict honest",
        s3["grounding_verdict"]
        in ("verified", "corrected", "unverified", "skipped"),
    )

    print("\n--- Scenario 4: ask atlas question scoped to meridian ---")
    sid_d = uuid.uuid4().hex
    s4 = chat(
        sid_d,
        "What port does the Atlas Protocol use?",
        web_enabled=False,
        doc_id=meridian["doc_id"],
    )
    print("trace:", trace_summary(s4["trace"]))
    print("answer:", s4["answer"][:300])
    check("s4 does NOT leak atlas port 5050", "5050" not in s4["answer"])
    check("s4 explicit refusal (no pivot)", is_refusal(s4["answer"]), s4["answer"][:120])
    retrieve4 = next((t for t in s4["trace"] if t.get("step") == "retrieve"), None)
    if retrieve4:
        files4 = {src.get("filename") for src in retrieve4.get("sources", [])}
        check(
            "s4 retrieval only touched meridian",
            files4 <= {"meridian-finance.pdf"},
            f"files={files4}",
        )

    print("\n--- Memory integrity check (live checkpointer state) ---")
    try:
        from app.agent.graph import build_graph, get_checkpointer

        reader_graph = build_graph(checkpointer=get_checkpointer())
        snap = reader_graph.get_state({"configurable": {"thread_id": sid_a}})
        msgs = snap.values.get("messages", [])
        types = [m.type for m in msgs]
        print(f"session {sid_a[:8]} message types: {types}")
        check(
            "memory: exactly 1 AI message per turn (2 turns -> 4 msgs)",
            types.count("ai") == 2 and len(types) == 4,
            f"types={types}",
        )
        last_ai = [m for m in msgs if m.type == "ai"][-1]
        check(
            "memory: last AI message equals final returned answer",
            last_ai.content.strip() == s2["answer"].strip(),
        )
        for sid in (sid_a, sid_c, sid_d):
            reader_graph.checkpointer.delete_thread(sid)
        print("(smoke-test threads removed from memory.sqlite)")
    except Exception as exc:  # noqa: BLE001
        check("memory integrity check", False, f"error: {exc}")

    print("\n--- Cleanup ---")
    r = requests.delete(f"{API}/documents/{atlas['doc_id']}", timeout=60)
    r.raise_for_status()
    r = requests.delete(f"{API}/documents/{meridian['doc_id']}", timeout=60)
    r.raise_for_status()
    final_docs = requests.get(f"{API}/documents", timeout=30).json()
    final_ids = {d["doc_id"] for d in final_docs}
    check(
        "cleanup: test docs removed, pre-existing store intact",
        final_ids == pre_ids,
        f"pre={pre_ids} final={final_ids}",
    )

    print("\n" + "=" * 60)
    print(f"RESULT: {len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("Failed checks:")
        for f in FAILED:
            print(f"  - {f}")
        sys.exit(1)
    print("ALL LIVE SMOKE CHECKS PASSED")


if __name__ == "__main__":
    main()
