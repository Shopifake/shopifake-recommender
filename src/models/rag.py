"""Models for RAG query processing and responses."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class RAGSearchRequest(BaseModel):
    """Incoming payload for RAG search submissions."""

    query: str = Field(..., min_length=3, description="Free-form query text")
    top_k: int | None = Field(
        default=None,
        ge=1,
        description="Number of similar products to retrieve",
    )
    score_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional cosine similarity threshold",
    )


class RAGSearchJob(BaseModel):
    """Representation of a queued RAG search job."""

    request_id: str
    query: str
    top_k: int
    score_threshold: float | None = None


class RAGSearchEnqueueResponse(BaseModel):
    """Acknowledgement returned after queueing a RAG search."""

    request_id: str
    status: Literal["queued"] = "queued"


class RAGSearchResultItem(BaseModel):
    """Single entry returned from Qdrant search."""

    product_id: str | None = None
    shop_id: str | None = None
    score: float
    description: str | None = None
    metadata: dict[str, Any] | None = None


class RAGSearchResultEnvelope(BaseModel):
    """Response body for polling RAG search status/results."""

    request_id: str
    status: Literal["queued", "processing", "complete", "failed"]
    results: list[RAGSearchResultItem] = Field(default_factory=list)
    error: str | None = None
    updated_at: str | None = None
