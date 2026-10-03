import os
import uuid
import requests
import streamlit as st

def _env_or_secret(key: str) -> str:
    """Read config from env vars, falling back to Streamlit Cloud secrets."""
    value = os.environ.get(key, "")
    if value:
        return value
    try:
        return st.secrets.get(key, "")  # type: ignore[attr-defined]
    except Exception:  # no secrets.toml — local dev
        return ""


API_BASE = _env_or_secret("API_BASE") or "http://localhost:8000"
API_KEY = _env_or_secret("INTELLINOTES_API_KEY")
REQUEST_TIMEOUT = 240


def _auth_headers() -> dict:
    """Headers sent with every backend request (no-op when auth is disabled)."""
    return {"X-API-Key": API_KEY} if API_KEY else {}

st.set_page_config(
    page_title="IntelliNotes — Agentic RAG Assistant",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling for modern dark UI aesthetics
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }
    
    .trace-card {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 10px;
    }
    
    .badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }
    .badge-notes { background-color: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); }
    .badge-web { background-color: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }
    .badge-direct { background-color: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); }
    .badge-verified { background-color: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }
    .badge-corrected { background-color: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }
    .badge-unverified { background-color: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }
    
    .source-chip {
        display: inline-block;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 6px;
        padding: 4px 10px;
        margin: 4px;
        font-size: 0.8rem;
    }
    
    .stButton>button {
        border-radius: 8px;
        transition: all 0.2s ease-in-out;
    }
    .stButton>button:hover {
        transform: translateY(-1px);
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def api_get(path):
    return requests.get(f"{API_BASE}{path}", headers=_auth_headers(), timeout=30)


def api_delete(path):
    return requests.delete(f"{API_BASE}{path}", headers=_auth_headers(), timeout=30)


def render_trace_timeline(trace):
    if not trace:
        st.caption("No trace data recorded for this step.")
        return

    for entry in trace:
        step = entry.get("step", "step")

        if step == "router":
            decision = entry.get("decision", "notes")
            badge_class = (
                "badge-notes"
                if decision == "notes"
                else "badge-web" if decision == "web" else "badge-direct"
            )
            st.markdown(
                f"""
                <div class="trace-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong>🧭 1. Routing Engine</strong>
                        <span class="badge {badge_class}">{decision.upper()}</span>
                    </div>
                    <p style="margin: 6px 0 0 0; font-size: 0.85rem; color: #94a3b8;">
                        {entry.get('reason', '')}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        elif step == "retrieve":
            st.markdown(
                f"""
                <div class="trace-card">
                    <strong>📚 2. Knowledge Base Retrieval</strong>
                    <p style="margin: 4px 0; font-size: 0.85rem; color: #94a3b8;">
                        {entry.get('detail', '')}
                    </p>
                    <small style="color: #64748b;">Query: <em>{entry.get('question_used', '')}</em></small>
                </div>
                """,
                unsafe_allow_html=True,
            )
            sources = entry.get("sources") or []
            if sources:
                chips = " ".join(
                    f'<span class="source-chip">📄 {s.get("filename", "doc")} (Page {s.get("page", 1)})</span>'
                    for s in sources
                )
                st.markdown(chips, unsafe_allow_html=True)

        elif step == "grade":
            decision = entry.get("decision", "insufficient")
            badge_color = "#34d399" if decision == "sufficient" else "#fbbf24"
            st.markdown(
                f"""
                <div class="trace-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong>⚖️ 3. Sufficiency Grader</strong>
                        <span style="color:{badge_color}; font-weight:600; font-size:0.8rem; text-transform:uppercase;">
                            ● {decision}
                        </span>
                    </div>
                    <p style="margin: 4px 0 0 0; font-size: 0.85rem; color: #94a3b8;">
                        {entry.get('reason', '')}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        elif step == "web_search":
            st.markdown(
                f"""
                <div class="trace-card">
                    <strong>🌐 4. Live Web Search Fallback</strong>
                    <p style="margin: 4px 0; font-size: 0.85rem; color: #94a3b8;">
                        {entry.get('detail', '')}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            for s in entry.get("sources") or []:
                st.markdown(f"- 🔗 [{s.get('title', 'Web Source')}]({s.get('url', '#')})")

        elif step == "synthesize":
            st.markdown(
                f"""
                <div class="trace-card">
                    <strong>✍️ 5. Synthesis & Citation</strong>
                    <p style="margin: 4px 0 0 0; font-size: 0.85rem; color: #94a3b8;">
                        {entry.get('detail', '')}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        elif step == "grounding":
            status = entry.get("status", "unverified")
            badge_class = (
                "badge-verified"
                if status == "verified"
                else "badge-corrected"
                if status == "corrected"
                else "badge-unverified"
                if status == "unverified"
                else "badge-direct"
            )
            st.markdown(
                f"""
                <div class="trace-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <strong>🛡️ 6. Self-RAG Anti-Hallucination Guard</strong>
                        <span class="badge {badge_class}">{status.upper()}</span>
                    </div>
                    <p style="margin: 4px 0 0 0; font-size: 0.85rem; color: #94a3b8;">
                        {entry.get('detail', '')}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )


# Initialize State
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex
if "last_upload_sig" not in st.session_state:
    st.session_state.last_upload_sig = None
if "selected_doc_id" not in st.session_state:
    st.session_state.selected_doc_id = None

# Sidebar
with st.sidebar:
    st.markdown("### ⚡ **IntelliNotes**")
    st.caption("Agentic RAG Assistant · Gemini · LangGraph · Tavily")
    st.divider()

    st.subheader("📤 Upload Document")
    uploaded = st.file_uploader(
        "Upload study notes, reports, or slides (PDF)", type=["pdf"], key="pdf_uploader"
    )

    if uploaded is not None:
        content = uploaded.getvalue()
        signature = (uploaded.name, uploaded.size, hash(content))
        if signature != st.session_state.last_upload_sig:
            with st.spinner("Extracting pages & indexing vectors..."):
                try:
                    response = requests.post(
                        f"{API_BASE}/upload-document/",
                        files={"file": (uploaded.name, content, "application/pdf")},
                        headers=_auth_headers(),
                        timeout=120,
                    )
                    response.raise_for_status()
                    body = response.json()
                    st.success(
                        f"Indexed **{body['filename']}** ({body['processed_chunks']} chunks)"
                    )
                    st.session_state.last_upload_sig = signature
                    st.rerun()
                except Exception as exc:
                    st.error(f"Upload failed: {exc}")

    # Fetch Documents
    documents = []
    try:
        docs_res = api_get("/documents")
        if docs_res.status_code == 200:
            documents = docs_res.json()
    except requests.RequestException:
        st.warning("⚠️ Backend service unreachable.")

    st.divider()
    st.subheader("📚 Document Scope")

    doc_options = {"all": "All Documents"}
    for doc in documents:
        doc_options[doc["doc_id"]] = f"{doc['filename']} ({doc['chunks']} chunks)"

    selected_key = st.selectbox(
        "Scope questions to:",
        options=list(doc_options.keys()),
        format_func=lambda x: doc_options[x],
        help="Filter vector retrieval to a specific document or search all documents.",
    )
    st.session_state.selected_doc_id = None if selected_key == "all" else selected_key

    if documents:
        with st.expander("Manage Documents", expanded=False):
            for doc in documents:
                col1, col2 = st.columns([4, 1])
                col1.caption(f"**{doc['filename']}** ({doc['chunks']} chunks)")
                if col2.button("🗑️", key=f"del_{doc['doc_id']}", help="Delete document"):
                    try:
                        resp = api_delete(f"/documents/{doc['doc_id']}")
                        if resp.status_code not in (200, 404):
                            st.error(f"Delete failed (HTTP {resp.status_code}).")
                    except requests.RequestException as exc:
                        st.error(f"Delete failed: {exc}")
                    st.rerun()

            if st.button("Clear All Documents", type="secondary"):
                try:
                    resp = api_delete("/documents/")
                    if resp.status_code != 200:
                        st.error(f"Clear failed (HTTP {resp.status_code}).")
                except requests.RequestException as exc:
                    st.error(f"Clear failed: {exc}")
                st.rerun()

    st.divider()
    web_enabled = st.toggle(
        "Allow Web Search Fallback",
        value=True,
        help="When notes context is insufficient, automatically retrieve fresh web results via Tavily.",
    )

    if st.button("New Conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.session_id = uuid.uuid4().hex
        st.rerun()

# Main Chat View
col_title, col_status = st.columns([3, 1])
with col_title:
    st.title("IntelliNotes")
    scope_label = (
        doc_options.get(selected_key, "All Documents")
        if selected_key != "all"
        else "All Documents"
    )
    st.caption(f"Current Scope: **{scope_label}** · Web Search: **{'Active' if web_enabled else 'Off'}**")

# Prompt Suggestion Chips for empty state
if not st.session_state.messages:
    st.info(
        "👋 **Welcome to IntelliNotes!** Upload a PDF document in the sidebar to ask questions about your notes. "
        "The agent will route queries, retrieve page-accurate chunks, verify grounding, and fallback to web search if needed."
    )
    st.markdown("##### 💡 Quick Start Suggestions")
    col1, col2, col3 = st.columns(3)
    preset_query = None
    if col1.button("📌 Summarize Key Points", use_container_width=True):
        preset_query = "Please provide a comprehensive summary of the key points in the document."
    if col2.button("🔍 Extract Main Takeaways", use_container_width=True):
        preset_query = "What are the most important conclusions and actionable takeaways?"
    if col3.button("❓ Core Concepts & Definitions", use_container_width=True):
        preset_query = "List and explain the main concepts and definitions discussed."

    if preset_query:
        st.session_state.messages.append({"role": "user", "content": preset_query})
        st.rerun()

# Render Message History
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("trace"):
            with st.expander("🔍 Inspect Agent Reasoning & Grounding Trace"):
                render_trace_timeline(message["trace"])

# Handle Chat Input
user_input = st.chat_input("Ask anything about your documents...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.rerun()

# If latest message is from user without assistant response, generate it
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    query_text = st.session_state.messages[-1]["content"]

    with st.chat_message("assistant"):
        with st.spinner("Analyzing notes, evaluating context & verifying grounding..."):
            try:
                response = requests.post(
                    f"{API_BASE}/chat/",
                    json={
                        "session_id": st.session_state.session_id,
                        "message": query_text,
                        "web_enabled": web_enabled,
                        "doc_id": st.session_state.selected_doc_id,
                    },
                    headers=_auth_headers(),
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                body = response.json()
            except requests.RequestException as exc:
                body = {
                    "answer": f"**Could not reach the backend service.**\n\n`{exc}`",
                    "grounding_verdict": "error",
                    "trace": [],
                }

        st.markdown(body["answer"])
        if body.get("trace"):
            with st.expander("🔍 Inspect Agent Reasoning & Grounding Trace", expanded=False):
                render_trace_timeline(body["trace"])

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": body["answer"],
            "grounding_verdict": body.get("grounding_verdict") or "unknown",
            "trace": body.get("trace", []),
        }
    )
    st.rerun()
