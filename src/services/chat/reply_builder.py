"""Generate natural-language replies for successful recommendations."""

from __future__ import annotations

import logging

from src.models.chat import ChatRecommendation, ChatRequest
from src.services.chat.history_utils import format_history_entry
from src.services.clients.decoder_client import DecoderClient

logger = logging.getLogger(__name__)


async def generate_reply(
    decoder: DecoderClient | None,
    payload: ChatRequest,
    recommendations: list[ChatRecommendation],
) -> str:
    if decoder is None:
        return default_reply(payload.query, recommendations)
    prompt = build_decoder_prompt(payload, recommendations)
    try:
        response = await decoder.decode(prompt)
        if response:
            return response.strip()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Decoder error, falling back to template: %s", exc)
    return default_reply(payload.query, recommendations)


def default_reply(query: str, recommendations: list[ChatRecommendation]) -> str:
    names = ", ".join(rec.name for rec in recommendations)
    return (
        f"Here are some options related to '{query.strip()}': {names}. "
        "Let me know if you need variations or more details."
    )


def build_decoder_prompt(
    payload: ChatRequest,
    recommendations: list[ChatRecommendation],
) -> str:
    product_lines = "\n".join(
        f"- {rec.name} (id: {rec.product_id})" for rec in recommendations
    )
    history_lines = "\n".join(format_history_entry(entry) for entry in payload.history)
    return (
        "You are a concise shopping assistant. Use the customer's context and "
        "the product list to craft a short helpful reply.\n"
        f"Conversation so far:\n{history_lines}\n"
        f"Latest question: {payload.query}\n"
        f"Suggested products:\n{product_lines}\n"
        "Answer in under 60 words."
    )
