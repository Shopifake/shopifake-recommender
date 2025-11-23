"""Redis-backed queue utilities for embedding jobs."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import redis.asyncio as redis

from src.config import settings
from src.models.embedding import EmbeddingJob

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    """Return a singleton Redis client for the current process."""

    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


class EmbeddingQueue:
    """High-level queue facade used by the API layer."""

    def __init__(self, client: redis.Redis, stream_key: str) -> None:
        self._client = client
        self._stream_key = stream_key

    async def enqueue(self, jobs: Sequence[EmbeddingJob]) -> int:
        """Push the provided jobs onto the Redis stream."""

        if not jobs:
            return 0

        for job in jobs:
            await self._client.xadd(
                name=self._stream_key,
                fields={"payload": job.model_dump_json()},
                id="*",
            )

        logger.info("Queued %s embedding jobs", len(jobs))
        return len(jobs)


def get_embedding_queue() -> EmbeddingQueue:
    client = get_redis_client()
    return EmbeddingQueue(client, settings.EMBEDDINGS_STREAM_KEY)
