"""Clarification helpers for the chat orchestrator."""

from __future__ import annotations

import logging

from src.models.chat import ChatRequest
from src.services.chat.history_utils import build_more_info_reply, format_history_entry
from src.services.clients.decoder_client import DecoderClient

logger = logging.getLogger(__name__)


async def generate_more_info_reply(
    decoder: DecoderClient | None,
    payload: ChatRequest,
) -> str:
    """Ask the decoder for additional context, fallback to template when needed."""
    if decoder is None:
        return build_more_info_reply(payload)
    prompt = _build_clarification_prompt(payload)
    try:
        reply = await decoder.decode(prompt)
        if reply:
            return reply.strip()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Decoder error during clarification prompt: %s", exc)
    return build_more_info_reply(payload)


def _build_clarification_prompt(payload: ChatRequest) -> str:
    history_lines = "\n".join(format_history_entry(entry) for entry in payload.history)
    question = payload.query.strip()
    return (
        "You are a shopping assistant asking the customer for details so you can "
        "run a perfect product search. Use the chat history for context and ask "
        "one precise follow-up question.\n"
        f"Conversation so far:\n{history_lines}\n"
        f"Latest user text: {question}\n"
        "Ask only for information that will help you match the product description "
        "to the user's needs.\n"
        "Do not ask about price or budget. Focus on attributes like recipient, "
        "interests, or usage scenario."
    )
