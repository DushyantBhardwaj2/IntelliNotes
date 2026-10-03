from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.ingestion.loader import Chunk

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "IntelliNotes API"
    assert "/chat/" in data["endpoints"]


def test_health_endpoint():
    with patch("app.ingestion.vectorstore.count_chunks", return_value=12):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["chunks_in_store"] == 12


def test_upload_non_pdf_rejected():
    files = {"file": ("test.txt", b"Hello world", "text/plain")}
    response = client.post("/upload-document/", files=files)
    assert response.status_code == 400
    assert "Only PDF files are supported" in response.json()["detail"]


@patch("app.main.load_pdf_chunks")
@patch("app.main.vectorstore.add_chunks")
@patch("app.main.vectorstore.count_chunks", return_value=3)
def test_upload_pdf_success(mock_count, mock_add, mock_load):
    mock_chunks = [
        Chunk(
            text="IntelliNotes chunk",
            metadata={"doc_id": "test_doc_id", "filename": "sample.pdf", "chunk_index": 0},
        )
    ]
    mock_load.return_value = mock_chunks

    files = {"file": ("sample.pdf", b"%PDF-fake", "application/pdf")}
    response = client.post("/upload-document/", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["doc_id"] == "test_doc_id"
    assert data["filename"] == "sample.pdf"
    assert data["processed_chunks"] == 1
    assert data["total_chunks_in_store"] == 3


@patch("app.main.load_pdf_chunks", return_value=[])
def test_upload_sparse_pdf_returns_400_not_500(mock_load):
    """A PDF that yields zero chunks must be a clean 400, not an IndexError 500."""
    files = {"file": ("sparse.pdf", b"%PDF-fake", "application/pdf")}
    response = client.post("/upload-document/", files=files)
    assert response.status_code == 400
    assert "No usable text chunks" in response.json()["detail"]


def test_upload_oversized_pdf_rejected():
    with patch.object(settings, "max_upload_mb", 0):
        files = {"file": ("huge.pdf", b"x" * 1024, "application/pdf")}
        response = client.post("/upload-document/", files=files)
    assert response.status_code == 413
    assert "upload limit" in response.json()["detail"]


@patch("app.main.get_graph")
def test_chat_endpoint_success(mock_get_graph):
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "answer": "Retrieval Augmented Generation enhances LLMs [Document: sample.pdf, Page: 1].",
        "grounding_verdict": "verified",
        "trace": [
            {"step": "router", "decision": "notes"},
            {"step": "retrieve", "detail": "1 chunk retrieved"},
            {"step": "grounding", "status": "verified"},
        ],
    }
    mock_get_graph.return_value = mock_graph

    payload = {
        "session_id": "session-xyz",
        "message": "What is RAG?",
        "web_enabled": True,
        "doc_id": "test_doc_id",
    }
    response = client.post("/chat/", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session-xyz"
    assert "Retrieval Augmented Generation" in data["answer"]
    assert data["grounding_verdict"] == "verified"
    assert len(data["trace"]) == 3


@patch("app.main.get_graph")
def test_chat_missing_grounding_verdict_returns_null(mock_get_graph):
    """If the graph result carries no verdict, the API must not fabricate one."""
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "answer": "Some answer.",
        "trace": [],
    }
    mock_get_graph.return_value = mock_graph

    payload = {"session_id": "session-null", "message": "Hello"}
    response = client.post("/chat/", json=payload)
    assert response.status_code == 200
    assert response.json()["grounding_verdict"] is None


@patch("app.main.vectorstore.delete_document")
@patch("app.main.vectorstore.count_chunks", return_value=0)
def test_delete_document(mock_count, mock_delete):
    mock_delete.return_value = 5
    response = client.delete("/documents/doc_123")
    assert response.status_code == 200
    data = response.json()
    assert data["doc_id"] == "doc_123"
    assert data["deleted_chunks"] == 5

    # 404 when document doesn't exist
    mock_delete.return_value = 0
    response_404 = client.delete("/documents/nonexistent")
    assert response_404.status_code == 404


@patch("app.main.vectorstore.clear_all", return_value=15)
def test_clear_all_documents(mock_clear):
    response = client.delete("/documents/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cleared"
    assert data["cleared_chunks"] == 15
