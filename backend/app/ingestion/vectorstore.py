import os
import threading
from typing import Any

from langchain_chroma import Chroma

from app.config import settings
from app.core.embeddings import get_embeddings
from app.ingestion.loader import Chunk

_STORE_LOCK = threading.Lock()
_VECTORSTORE: Chroma | None = None


def _clean_env() -> dict[str, str]:
    """Chroma telemetry env with posthog/anonymized-telemetry fully disabled."""
    return {
        "ANONYMIZED_TELEMETRY": "False",
        "ALLOW_CHROMA_TELEMETRY_RECORDING": "False",
        "POSTHOG_API_KEY": "",
        "POSTHOG_HOST": "",
    }


def _telemetry_off() -> None:
    """Force-disable Chroma telemetry before its client can initialize."""
    for key, value in _clean_env().items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)


def get_vectorstore() -> Chroma:
    global _VECTORSTORE
    if _VECTORSTORE is None:
        with _STORE_LOCK:
            if _VECTORSTORE is None:
                _telemetry_off()
                _VECTORSTORE = Chroma(
                    collection_name=settings.collection_name,
                    embedding_function=get_embeddings(),
                    persist_directory=str(settings.chroma_path),
                )
    return _VECTORSTORE


def add_chunks(chunks: list[Chunk]) -> int:
    if not chunks:
        return 0
    store = get_vectorstore()
    store.add_texts(
        texts=[chunk.text for chunk in chunks],
        metadatas=[chunk.metadata for chunk in chunks],
        ids=[
            f"{chunk.metadata['doc_id']}-{chunk.metadata['chunk_index']}"
            for chunk in chunks
        ],
    )
    return len(chunks)


def search_notes(
    query: str,
    doc_id: str | None = None,
    k: int | None = None,
) -> list[dict[str, Any]]:
    store = get_vectorstore()
    filter_dict = {"doc_id": doc_id} if doc_id else None
    
    if filter_dict:
        docs = store.similarity_search(query, k=k or settings.top_k, filter=filter_dict)
    else:
        docs = store.similarity_search(query, k=k or settings.top_k)

    return [
        {"text": doc.page_content, "metadata": doc.metadata} for doc in docs
    ]


def count_chunks(doc_id: str | None = None) -> int:
    store = get_vectorstore()
    if doc_id:
        records = store._collection.get(where={"doc_id": doc_id}, include=[])
        return len(records.get("ids", []))
    return int(store._collection.count())


def delete_document(doc_id: str) -> int:
    """Delete all chunks belonging to a specific doc_id from Chroma."""
    store = get_vectorstore()
    # Check count first
    existing = store._collection.get(where={"doc_id": doc_id}, include=[])
    ids = existing.get("ids", [])
    if ids:
        store._collection.delete(where={"doc_id": doc_id})
    return len(ids)


def clear_all() -> int:
    """Remove all documents and reset the collection."""
    global _VECTORSTORE
    store = get_vectorstore()
    count = int(store._collection.count())
    with _STORE_LOCK:
        try:
            store.delete_collection()
        except Exception:
            # Fallback if collection was empty or delete failed
            existing = store._collection.get(include=[])
            if existing.get("ids"):
                store._collection.delete(ids=existing["ids"])
        _VECTORSTORE = None
    return count


def list_documents() -> list[dict[str, Any]]:
    store = get_vectorstore()
    records = store._collection.get(include=["metadatas"])
    documents: dict[str, dict[str, Any]] = {}
    for metadata in records.get("metadatas") or []:
        doc_id = metadata.get("doc_id")
        if not doc_id:
            continue
        if doc_id not in documents:
            documents[doc_id] = {
                "doc_id": doc_id,
                "filename": metadata.get("filename", "unknown"),
                "chunks": 0,
            }
        documents[doc_id]["chunks"] += 1
    return list(documents.values())

