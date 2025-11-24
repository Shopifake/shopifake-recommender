"""Dead Letter Queue manager for failed message handling."""

from __future__ import annotations

import logging

from src.config import settings
from src.services.queue.redis_stream import RedisStreamService

logger = logging.getLogger(__name__)


class DLQManager:
    """Manager for handling dead letter queue operations."""

    def __init__(self, redis_service: RedisStreamService):
        self.redis_service = redis_service
        self.dlq_stream = settings.DLQ_STREAM_KEY

    async def send_to_dlq(
        self,
        entry_id: str,
        payload: str,
        error: Exception,
        original_stream: str | None = None,
    ) -> None:
        """Send a failed message to the dead letter queue."""
        try:
            await self.redis_service.add_to_stream(
                fields={
                    "payload": payload,
                    "error": str(error),
                    "entry_id": entry_id,
                    "original_stream": original_stream or self.redis_service.stream_key,
                },
                stream_key=self.dlq_stream,
            )
            logger.warning(
                "Message sent to DLQ",
                extra={
                    "entry_id": entry_id,
                    "dlq_stream": self.dlq_stream,
                    "error": str(error),
                },
            )
        except Exception as dlq_error:
            logger.error(
                "Failed to send message to DLQ: %s",
                dlq_error,
                extra={"entry_id": entry_id, "original_error": str(error)},
                exc_info=True,
            )


def create_dlq_manager(redis_service: RedisStreamService) -> DLQManager:
    """Factory function to create a DLQ manager."""
    return DLQManager(redis_service)
