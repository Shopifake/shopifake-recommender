"""Utility helpers for persisting RAG search results in Redis."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import redis.asyncio as redis

from src.config import settings


class RAGResultStore:
    """Wrapper around Redis used to store/poll RAG search results."""

    def __init__(self, client: redis.Redis):
        self._client = client
        self._ttl = settings.RAG_RESULT_TTL_SECONDS

    def _key(self, request_id: str) -> str:
        return f"{settings.RAG_RESULT_KEY_PREFIX}{request_id}"

    async def initialize(self, request_id: str) -> None:
        payload = {
            "request_id": request_id,
            "status": "queued",
            "results": [],
            "updated_at": self._timestamp(),
        }
        await self._client.set(self._key(request_id), json.dumps(payload), ex=self._ttl)

    async def mark_processing(self, request_id: str) -> None:
        await self._update_status(request_id, "processing")

    async def save_success(self, request_id: str, results: list[dict]) -> None:
        payload = {
            "request_id": request_id,
            "status": "complete",
            "results": results,
            "updated_at": self._timestamp(),
        }
        await self._client.set(self._key(request_id), json.dumps(payload), ex=self._ttl)

    async def save_failure(self, request_id: str, error: str) -> None:
        payload = {
            "request_id": request_id,
            "status": "failed",
            "error": error,
            "results": [],
            "updated_at": self._timestamp(),
        }
        await self._client.set(self._key(request_id), json.dumps(payload), ex=self._ttl)

    async def fetch(self, request_id: str) -> dict | None:
        raw = await self._client.get(self._key(request_id))
        if not raw:
            return None
        return json.loads(raw)

    async def _update_status(self, request_id: str, status: str) -> None:
        existing = await self.fetch(request_id)
        payload = existing or {
            "request_id": request_id,
            "results": [],
        }
        payload["status"] = status
        payload["updated_at"] = self._timestamp()
        await self._client.set(self._key(request_id), json.dumps(payload), ex=self._ttl)

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()
