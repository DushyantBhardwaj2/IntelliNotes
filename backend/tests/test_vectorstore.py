import pytest
from unittest.mock import patch
from langchain_chroma import Chroma
from langchain_core.embeddings import FakeEmbeddings

from app.ingestion.loader import Chunk
from app.ingestion import vectorstore


@pytest.fixture(autouse=True)
def mock_chroma_env(tmp_path):
    """Isolate each test in a clean temporary directory with deterministic fake embeddings."""
    fake_embeddings = FakeEmbeddings(size=768)
    test_store = Chroma(
        collection_name="test_collection",
        embedding_function=fake_embeddings,
        persist_directory=str(tmp_path / "chroma"),
    )
    
    with patch("app.ingestion.vectorstore.get_vectorstore", return_value=test_store):
        yield




def test_add_and_count_chunks():
    chunks = [
        Chunk(
            text="IntelliNotes provides agentic RAG for PDF notes.",
            metadata={"doc_id": "doc_1", "filename": "file1.pdf", "chunk_index": 0, "page_number": 1},
        ),
        Chunk(
            text="LangGraph coordinates routing, retrieval, and grading nodes.",
            metadata={"doc_id": "doc_1", "filename": "file1.pdf", "chunk_index": 1, "page_number": 1},
        ),
    ]
    added = vectorstore.add_chunks(chunks)
    assert added == 2
    assert vectorstore.count_chunks() == 2
    assert vectorstore.count_chunks("doc_1") == 2
    assert vectorstore.count_chunks("doc_nonexistent") == 0


def test_search_notes_and_scoping():
    doc1_chunks = [
        Chunk(
            text="Quantum computing utilizes qubits and superposition principles.",
            metadata={"doc_id": "physics_doc", "filename": "physics.pdf", "chunk_index": 0, "page_number": 1},
        )
    ]
    doc2_chunks = [
        Chunk(
            text="The federal reserve oversees monetary policy and interest rates.",
            metadata={"doc_id": "economics_doc", "filename": "econ.pdf", "chunk_index": 0, "page_number": 1},
        )
    ]
    vectorstore.add_chunks(doc1_chunks)
    vectorstore.add_chunks(doc2_chunks)

    # Search without scoping returns results from any document
    results = vectorstore.search_notes("superposition", k=2)
    assert len(results) >= 1

    # Search with doc_id scoping strictly returns matching document chunks
    scoped_physics = vectorstore.search_notes("monetary policy", doc_id="physics_doc", k=2)
    for r in scoped_physics:
        assert r["metadata"]["doc_id"] == "physics_doc"

    scoped_econ = vectorstore.search_notes("qubits", doc_id="economics_doc", k=2)
    for r in scoped_econ:
        assert r["metadata"]["doc_id"] == "economics_doc"


def test_list_and_delete_document():
    chunks = [
        Chunk(
            text="Chemistry reactions and stoichiometry equations.",
            metadata={"doc_id": "chem_doc", "filename": "chem.pdf", "chunk_index": 0, "page_number": 1},
        ),
        Chunk(
            text="Biology ecosystems and energy pyramids.",
            metadata={"doc_id": "bio_doc", "filename": "bio.pdf", "chunk_index": 0, "page_number": 1},
        ),
    ]
    vectorstore.add_chunks(chunks)

    docs = vectorstore.list_documents()
    assert len(docs) == 2
    doc_ids = {d["doc_id"] for d in docs}
    assert "chem_doc" in doc_ids
    assert "bio_doc" in doc_ids

    # Delete chem_doc
    deleted_count = vectorstore.delete_document("chem_doc")
    assert deleted_count == 1
    assert vectorstore.count_chunks() == 1
    
    remaining_docs = vectorstore.list_documents()
    assert len(remaining_docs) == 1
    assert remaining_docs[0]["doc_id"] == "bio_doc"
