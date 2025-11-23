"""Models used by the embedding ingestion API and worker."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class EmbeddingJob(BaseModel):
    """Represents a single product embedding job sent from the catalog."""

    product_id: str = Field(..., min_length=1)
    shop_id: str = Field(..., min_length=1)
    version: int | None = Field(
        default=None,
        description="Optional monotonically increasing version used for idempotency",
    )
    embed_text: str = Field(..., min_length=1, description="Text body to embed")
    metadata: dict = Field(default_factory=dict)
    op: Literal["create", "update", "delete"] = Field(
        default="create",
        description="Indicates the requested action for the vector store",
    )
    trace_id: str | None = Field(
        default=None,
        description="Optional trace identifier propagated from the catalog service",
    )


class EmbeddingBatch(BaseModel):
    """Request body for POST /v1/embeddings."""

    items: list[EmbeddingJob] = Field(..., min_length=1)

    @field_validator("items")
    @classmethod
    def _limit_items(cls, values: list[EmbeddingJob]) -> list[EmbeddingJob]:
        if len(values) > 500:
            raise ValueError("Batch size must be <= 500 items")
        return values


class EmbeddingEnqueueResponse(BaseModel):
    """Response body for embedding ingestion request."""

    queued: int = Field(..., ge=0)
