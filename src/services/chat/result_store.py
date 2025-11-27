"""Redis-backed persistence for chat orchestration results."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import redis.asyncio as redis

from src.config import settings
from src.models.chat import ChatRecommendation, ChatResultEnvelope, ChatResultPayload


class ChatResultStore:
    """Wrapper responsible for persisting chat results in Redis."""

    def __init__(self, client: redis.Redis):
        self._client = client
        self._prefix = settings.CHAT_RESULT_KEY_PREFIX
        self._ttl = settings.CHAT_RESULT_TTL_SECONDS

    def _key(self, request_id: str) -> str:
        return f"{self._prefix}{request_id}"

    async def initialize(self, request_id: str) -> None:
        payload = ChatResultEnvelope(request_id=request_id).model_dump()
        await self._client.set(self._key(request_id), json.dumps(payload), ex=self._ttl)

    async def save_success(self, request_id: str, result: ChatResultPayload) -> None:
        payload = ChatResultEnvelope(
            request_id=request_id,
            status="complete",
            reply=result.reply,
            decoder_satisfaction=result.decoder_satisfaction,
            recommendations=result.recommendations,
            updated_at=self._timestamp(),
        ).model_dump()
        await self._client.set(self._key(request_id), json.dumps(payload), ex=self._ttl)

    async def save_failure(self, request_id: str, error: str) -> None:
        payload = ChatResultEnvelope(
            request_id=request_id,
            status="failed",
            error=error,
            updated_at=self._timestamp(),
        ).model_dump()
        await self._client.set(self._key(request_id), json.dumps(payload), ex=self._ttl)

    async def fetch(self, request_id: str) -> ChatResultEnvelope | None:
        raw = await self._client.get(self._key(request_id))
        if not raw:
            return None
        data = json.loads(raw)
        return ChatResultEnvelope(**data)

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()


def serialize_recommendations(
    recommendations: list[ChatRecommendation],
) -> list[dict[str, str]]:
    """Helper used by tests to serialize recommendation models."""

    return [rec.model_dump() for rec in recommendations]
