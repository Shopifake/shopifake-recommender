"""RAG helper functions used by the chat orchestrator."""

from __future__ import annotations

import logging
from typing import Any

from src.config import settings
from src.models.chat import ChatRecommendation, ChatRequest
from src.services.chat.history_utils import extract_last_user_message
from src.services.clients.decoder_client import DecoderClient
from src.services.clients.encoder_client import EncoderClient
from src.services.storage.qdrant_service import QdrantService

logger = logging.getLogger(__name__)


async def rewrite_as_rag_query(
    payload: ChatRequest,
    decoder: DecoderClient | None,
) -> str:
    print("[ChatRAG] Rewriting chat history and query for RAG search...")
    if decoder is None:
        print("[ChatRAG] No decoder available, using raw query.")
        return payload.query.strip()
    history_lines = []
    for entry in payload.history:
        role = getattr(entry, "role", None)
        if role == "rag":
            history_lines.append(f"rag: {entry.content.reply}")
        else:
            history_lines.append(f"user: {entry.content}")
    prompt = (
        "Rewrite the following chat history and latest question as a concise "
        "product search query for a recommender system.\n"
        f"History:\n{chr(10).join(history_lines)}\n"
        f"Latest question: {payload.query.strip()}\n"
        "Output only the search query, no explanation."
    )
    print(f"[ChatRAG] Decoder prompt for RAG query: '{prompt}'")
    try:
        rag_query = await decoder.decode(prompt)
        print(f"[ChatRAG] Decoder returned RAG query: '{rag_query.strip()}'")
        return rag_query.strip()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Decoder error during RAG query rewrite: %s", exc)
        print(f"[ChatRAG] Decoder error: {exc}. Using raw query.")
        return payload.query.strip()


async def search_recommendations_with_rag_query(
    payload: ChatRequest,
    rag_query: str,
    encoder: EncoderClient | None,
    qdrant_service: QdrantService,
) -> list[ChatRecommendation]:
    print(f"[ChatRAG] Searching recommendations for RAG query: '{rag_query}'")
    top_k = resolve_top_k(payload.params)
    text = rag_query
    if not text or encoder is None:
        print(
            "[ChatRAG] No text or encoder available, returning empty recommendations."
            f"text: {text}, encoder: {encoder}"
            f"top_k: {top_k}"
            f"qdrant_service: {qdrant_service}"
            f"payload: {payload}"
            f"rag_query: {rag_query}"
            f"encoder: {encoder}"
            f"qdrant_service: {qdrant_service}"
            f"payload: {payload}"
            f"rag_query: {rag_query}"
        )
        return []
    vector = await _encode_text(encoder, text)
    print(f"[ChatRAG] Encoded vector (first 5): {vector[:5]}")
    hits = await _query_vector_store(qdrant_service, vector, top_k)
    print(f"[ChatRAG] Vector store hits: {hits}")
    candidates = convert_hits_to_recommendations(hits, payload.site_id, top_k)
    print(f"[ChatRAG] Converted recommendations: {candidates}")
    return candidates


def resolve_top_k(params: dict[str, Any] | None) -> int:
    if not params:
        return settings.CHAT_DEFAULT_TOP_K
    try:
        top_k = int(params.get("top_k", settings.CHAT_DEFAULT_TOP_K))
    except (TypeError, ValueError):
        return settings.CHAT_DEFAULT_TOP_K
    return max(1, min(top_k, settings.RAG_MAX_TOP_K))


def convert_hits_to_recommendations(
    hits: list[dict[str, Any]],
    site_id: str,
    top_k: int,
) -> list[ChatRecommendation]:
    recommendations: list[ChatRecommendation] = []
    for hit in hits:
        payload_data: dict[str, Any] = hit.get("payload") or {}
        if payload_data.get("shop_id") not in (None, site_id):
            continue
        product_id = payload_data.get("product_id") or str(hit.get("id"))
        name = payload_data.get("name")
        if not name:
            metadata = payload_data.get("metadata") or {}
            name = metadata.get("name") or metadata.get("title")
        if not product_id or not name:
            continue
        recommendations.append(ChatRecommendation(product_id=product_id, name=name))
        if len(recommendations) >= top_k:
            break
    return recommendations


def compose_embedding_text(payload: ChatRequest) -> str:
    pieces = [payload.query.strip()]
    last_user = extract_last_user_message(payload.history)
    if last_user:
        pieces.append(last_user)
    return " \n".join(piece for piece in pieces if piece).strip()


async def _encode_text(encoder: EncoderClient, text: str) -> list[float]:
    return await encoder.embed(text)


async def _query_vector_store(
    qdrant_service: QdrantService,
    vector: list[float],
    top_k: int,
) -> list[dict[str, Any]]:
    try:
        return await qdrant_service.search_similar(vector, limit=top_k)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Falling back to static catalog suggestions: %s", exc)
        return []
