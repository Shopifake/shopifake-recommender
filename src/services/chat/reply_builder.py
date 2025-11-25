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
            import json

            try:
                data = json.loads(response)
                reply = data.get("reply")
                recs = data.get("recommendations")
                # Validate recommendations format
                if (
                    isinstance(reply, str)
                    and isinstance(recs, list)
                    and all(
                        isinstance(r, dict) and "product_id" in r and "name" in r
                        for r in recs
                    )
                ):
                    # Return reply and recommendations as expected
                    return reply, recs
            except Exception as json_exc:
                logger.warning("Decoder did not return valid JSON: %s", json_exc)
            # Fallback: treat as plain text
            return response.strip(), recommendations
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Decoder error, falling back to template: %s", exc)
    return default_reply(payload.query, recommendations), recommendations


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
        "You are a shopping assistant. "
        "Based on the conversation and the suggested products below, select the best product(s) for the user. "
        "Your response MUST be a JSON object with two fields: "
        "'reply' (a short natural-language answer) and "
        "'recommendations' (an array of product objects, each with 'product_id' and 'name',\n"
        "chosen from the suggested products list). "
        "Do not invent or suggest products that are not in the list.\n"
        f"Conversation so far:\n{history_lines}\n"
        f"Latest question: {payload.query}\n"
        f"Suggested products:\n{product_lines}\n"
        "Respond ONLY with valid JSON."
    )
