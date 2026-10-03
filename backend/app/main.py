import re
import warnings

warnings.filterwarnings("ignore", message=".*automatic function calling.*")

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage

from app.agent.graph import get_checkpointer, get_graph
from app.config import settings
from app.ingestion import vectorstore
from app.ingestion.loader import load_pdf_chunks
from app.security import (
    client_identity,
    make_chat_limiter,
    make_upload_limiter,
    redact_secrets,
    require_api_key,
    sanitize_detail,
)
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ClearResponse,
    DeleteResponse,
    DocumentInfo,
    UploadResponse,
)

app = FastAPI(
    title="IntelliNotes API",
    description=(
        "Agentic RAG knowledge assistant: chat over your uploaded PDF notes "
        "with automatic web-search fallback, grounding verification, and a transparent agent trace."
    ),
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key"],
)

@app.on_event("startup")
def startup_event():
    try:
        get_checkpointer()
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("Startup checkpointer initialization notice: %s", exc)

chat_limiter = make_chat_limiter()
upload_limiter = make_upload_limiter()


@app.get("/")
def root():
    return {
        "name": "IntelliNotes API",
        "docs": "/docs",
        "endpoints": [
            "/chat/",
            "/upload-document/",
            "/documents",
            "/documents/{doc_id}",
            "/health",
        ],
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": settings.chat_model,
        "chunks_in_store": vectorstore.count_chunks(),
    }


@app.post("/chat/", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
def chat(request: ChatRequest, request_obj: Request):
    # Per-IP limiting. With a single shared API key behind a server-side
    # frontend proxy, the client IP (X-Forwarded-For aware) is the real
    # differentiator — keying by the shared key would create one global bucket.
    chat_limiter.check(client_identity(request_obj))
    try:
        graph = get_graph()
        result = graph.invoke(
            {
                "messages": [HumanMessage(content=request.message)],
                "question": request.message,
                "web_enabled": request.web_enabled,
                "doc_id": request.doc_id,
            },
            config={"configurable": {"thread_id": request.session_id}},
        )
    except Exception as exc:  # noqa: BLE001
        # Full detail goes to server logs; the client gets a generic message.
        raise HTTPException(status_code=503, detail=sanitize_detail(exc)) from exc

    return ChatResponse(
        session_id=request.session_id,
        answer=result.get("answer", ""),
        grounding_verdict=result.get("grounding_verdict"),
        trace=redact_secrets(result.get("trace", [])),
    )


@app.post(
    "/upload-document/",
    response_model=UploadResponse,
    dependencies=[Depends(require_api_key)],
)
def upload_document(request: Request, file: UploadFile = File(...)):
    filename = file.filename or "document.pdf"
    # Strict check: reject paths, hidden files, multiple extensions, non-pdf
    if not re.fullmatch(r"[a-zA-Z0-9_\-][^/\\:]*\.pdf", filename, flags=re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    upload_limiter.check(client_identity(request))

    max_bytes = settings.max_upload_mb * 1024 * 1024
    pdf_bytes = file.file.read(max_bytes + 1)
    if len(pdf_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_upload_mb} MB upload limit.",
        )

    try:
        chunks = load_pdf_chunks(pdf_bytes, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not chunks:
        raise HTTPException(
            status_code=400,
            detail="No usable text chunks could be extracted from this PDF.",
        )

    vectorstore.add_chunks(chunks)

    return UploadResponse(
        doc_id=chunks[0].metadata["doc_id"],
        filename=filename,
        processed_chunks=len(chunks),
        total_chunks_in_store=vectorstore.count_chunks(),
    )


@app.get("/documents", response_model=list[DocumentInfo], dependencies=[Depends(require_api_key)])
def documents():
    return vectorstore.list_documents()


@app.delete(
    "/documents/{doc_id}",
    response_model=DeleteResponse,
    dependencies=[Depends(require_api_key)],
)
def delete_document(doc_id: str):
    deleted = vectorstore.delete_document(doc_id)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Document not found.")
    return DeleteResponse(
        doc_id=doc_id,
        deleted_chunks=deleted,
        remaining_chunks=vectorstore.count_chunks(),
    )


@app.delete(
    "/documents/",
    response_model=ClearResponse,
    dependencies=[Depends(require_api_key)],
)
def clear_documents():
    cleared = vectorstore.clear_all()
    return ClearResponse(status="cleared", cleared_chunks=cleared)

