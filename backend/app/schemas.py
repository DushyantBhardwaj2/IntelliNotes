import uuid

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    message: str = Field(min_length=1, max_length=4000)
    web_enabled: bool = True
    doc_id: str | None = Field(
        default=None,
        description="Optional document ID to scope retrieval to a specific document.",
    )


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    grounding_verdict: str | None = None
    trace: list[dict]


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    processed_chunks: int
    total_chunks_in_store: int


class DocumentInfo(BaseModel):
    doc_id: str
    filename: str
    chunks: int


class DeleteResponse(BaseModel):
    doc_id: str
    deleted_chunks: int
    remaining_chunks: int


class ClearResponse(BaseModel):
    status: str
    cleared_chunks: int

