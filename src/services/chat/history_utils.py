"""Utilities to inspect previous chat interactions."""

from __future__ import annotations

from collections.abc import Iterable

from src.models.chat import ChatHistoryEntry, ChatRequest


def needs_more_info(payload: ChatRequest) -> bool:
    """Determine whether the assistant should ask the user for more context."""
    tokens = payload.query.strip().split()
    has_rag_entry = _has_rag_role(payload.history)
    if not has_rag_entry:
        return True
    last_rag = _last_rag_entry(payload.history)
    if last_rag and not getattr(last_rag.content, "recommendations", []):
        return len(tokens) <= 3
    return False


def build_more_info_reply(payload: ChatRequest) -> str:
    """Fallback clarification message when decoder assistance is unavailable."""
    prompt = payload.query.strip().rstrip("?.! ") or "your request"
    return (
        "I'd love to help you find something special. Could you tell me more about "
        f"'{prompt}'? Who is it for and what do they enjoy?"
    )


def extract_last_user_message(history: Iterable[ChatHistoryEntry]) -> str | None:
    for entry in reversed(list(history)):
        if getattr(entry, "role", None) == "user":
            content = getattr(entry, "content", None)
            if isinstance(content, str):
                return content
    return None


def format_history_entry(entry: ChatHistoryEntry) -> str:
    if getattr(entry, "role", None) == "rag":
        return f"rag: {entry.content.reply}"
    return f"user: {entry.content}"


def _has_rag_role(history: Iterable[ChatHistoryEntry]) -> bool:
    return any(getattr(entry, "role", None) == "rag" for entry in history)


def _last_rag_entry(history: Iterable[ChatHistoryEntry]) -> ChatHistoryEntry | None:
    for entry in reversed(list(history)):
        if getattr(entry, "role", None) == "rag":
            return entry
    return None
