"""Redis stream service for message queue operations."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import redis.asyncio as redis  # type: ignore[import]
from redis.exceptions import ResponseError  # type: ignore[import]

from src.config import settings

logger = logging.getLogger(__name__)


class RedisStreamService:
    """Service for Redis stream operations."""

    def __init__(self, client: redis.Redis, stream_key: str, group_name: str):
        self.client = client
        self.stream_key = stream_key
        self.group_name = group_name

    async def ensure_consumer_group(self) -> None:
        """Ensure the consumer group exists."""
        try:
            await self.client.xgroup_create(
                name=self.stream_key,
                groupname=self.group_name,
                id="0",
                mkstream=True,
            )
            logger.info(
                "Created Redis consumer group", extra={"group": self.group_name}
            )
        except ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                logger.debug(
                    "Consumer group already exists", extra={"group": self.group_name}
                )
                return
            logger.error("Failed to create consumer group: %s", exc, exc_info=True)
            raise

    async def read_batch(
        self,
        consumer_name: str,
        count: int = 10,
        block_ms: int = 5000,
    ) -> list[tuple[str, Sequence[tuple[str, dict[str, str]]]]]:
        """Read a batch of messages from the stream."""
        try:
            return await self.client.xreadgroup(
                groupname=self.group_name,
                consumername=consumer_name,
                streams={self.stream_key: ">"},
                count=count,
                block=block_ms,
            )
        except ResponseError as exc:
            if "NOGROUP" in str(exc):
                logger.warning("Consumer group missing, recreating: %s", exc)
                await self.ensure_consumer_group()
                return await self.client.xreadgroup(
                    groupname=self.group_name,
                    consumername=consumer_name,
                    streams={self.stream_key: ">"},
                    count=count,
                    block=block_ms,
                )
            raise

    async def acknowledge_messages(self, message_ids: list[str]) -> None:
        """Acknowledge processed messages."""
        if message_ids:
            await self.client.xack(self.stream_key, self.group_name, *message_ids)

    async def delete_messages(self, message_ids: list[str]) -> None:
        """Delete acknowledged messages from the stream."""
        if message_ids:
            await self.client.xdel(self.stream_key, *message_ids)

    async def add_to_stream(
        self, fields: dict[str, str], stream_key: str | None = None
    ) -> str:
        """Add a message to a stream."""
        key = stream_key or self.stream_key
        return await self.client.xadd(key, fields)


def create_redis_stream_service(
    stream_key: str | None = None,
    group_name: str | None = None,
) -> RedisStreamService:
    """Factory function to create a Redis stream service."""
    client = redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        health_check_interval=30,
    )
    stream = stream_key or settings.EMBEDDINGS_STREAM_KEY
    group = group_name or settings.EMBEDDINGS_CONSUMER_GROUP
    return RedisStreamService(client, stream, group)
