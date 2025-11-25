"""Schemas used by the chat orchestration API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRecommendation(BaseModel):
    """Minimal product data returned to the UI."""

    product_id: str
    name: str


class ChatRagContent(BaseModel):
    """Payload stored in a RAG-generated history entry."""

    reply: str = Field(..., min_length=1)
    recommendations: list[ChatRecommendation] = Field(default_factory=list)


class ChatUserMessage(BaseModel):
    """User-authored history message."""

    role: Literal["user"] = "user"
    content: str = Field(..., min_length=1)


class ChatRagMessage(BaseModel):
    """Assistant-authored history message."""

    role: Literal["rag"] = "rag"
    content: ChatRagContent


ChatHistoryEntry = ChatUserMessage | ChatRagMessage


class ChatRequest(BaseModel):
    """Incoming payload for POST /chat."""

    site_id: str
    history: list[ChatHistoryEntry] = Field(default_factory=list)
    query: str = Field(..., min_length=1)
    params: dict[str, Any] | None = None


class ChatEnqueueResponse(BaseModel):
    """Acknowledgement returned when a chat request is accepted."""

    request_id: str
    status: Literal["pending"] = "pending"


class ChatResultEnvelope(BaseModel):
    """Response returned by GET /chat/result/{request_id}."""

    request_id: str
    status: Literal["pending", "complete", "failed"] = "pending"
    reply: str | None = None
    decoder_satisfaction: (
        Literal[
            "satisfied",
            "unsatisfied",
            "need_more_info",
        ]
        | None
    ) = None
    recommendations: list[ChatRecommendation] = Field(default_factory=list)
    error: str | None = None
    updated_at: str | None = None


class ChatResultPayload(BaseModel):
    """Internal representation of a completed chat run."""

    reply: str
    decoder_satisfaction: Literal["satisfied", "unsatisfied", "need_more_info"]
    recommendations: list[ChatRecommendation]
