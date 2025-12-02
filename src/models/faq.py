"""Schemas used by the FAQ chatbot API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FaqUserMessage(BaseModel):
    """A message sent by the user in the FAQ conversation."""

    role: Literal["user"] = "user"
    content: str = Field(..., min_length=1, description="The user's message content")


class FaqAssistantMessage(BaseModel):
    """A message sent by the FAQ assistant."""

    role: Literal["assistant"] = "assistant"
    content: str = Field(..., min_length=1, description="The assistant's response content")


FaqHistoryEntry = FaqUserMessage | FaqAssistantMessage
"""A single entry in the FAQ conversation history, either from user or assistant."""


class FaqRequest(BaseModel):
    """Request payload for the FAQ answer endpoint."""

    message: str = Field(
        ...,
        min_length=1,
        description="The user's question to be answered",
    )
    conversation_history: list[FaqHistoryEntry] = Field(
        default_factory=list,
        description="Previous messages in the conversation for context",
    )


class FaqResponse(BaseModel):
    """Response payload from the FAQ answer endpoint."""

    answer: str = Field(..., description="The chatbot's answer to the user's question")

