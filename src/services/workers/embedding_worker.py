"""Refactored embedding worker using modular services."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from collections.abc import Sequence

from src.config import settings
from src.models.embedding import EmbeddingJob
from src.services.clients.encoder_client import EncoderClient, get_encoder_client
from src.services.queue.dlq_manager import DLQManager, create_dlq_manager
from src.services.queue.redis_stream import (
    RedisStreamService,
    create_redis_stream_service,
)
from src.services.storage.qdrant_service import QdrantService, create_qdrant_service
from src.services.workers.base import BaseWorker

logger = logging.getLogger(__name__)


class EmbeddingWorker(BaseWorker):
    """Refactored embedding worker using modular services."""

    def __init__(
        self,
        *,
        redis_service: RedisStreamService,
        qdrant_service: QdrantService,
        dlq_manager: DLQManager,
        encoder: EncoderClient,
        consumer_name: str | None = None,
    ) -> None:
        super().__init__(consumer_name)
        self.redis_service = redis_service
        self.qdrant_service = qdrant_service
        self.dlq_manager = dlq_manager
        self.encoder = encoder
        self.batch_size = settings.BATCH_MAX_MESSAGES
        self.block_ms = settings.BATCH_MAX_WAIT_MS

    async def run_forever(self) -> None:
        """Main worker loop."""
        await self.redis_service.ensure_consumer_group()

        logger.info(
            "Embedding worker started",
            extra={
                "stream": self.redis_service.stream_key,
                "group": self.redis_service.group_name,
                "consumer": self.consumer_name,
            },
        )

        try:
            while not self.is_shutdown_requested():
                try:
                    entries = await self.redis_service.read_batch(
                        consumer_name=self.consumer_name,
                        count=self.batch_size,
                        block_ms=self.block_ms,
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to read from Redis stream: %s", exc, exc_info=True
                    )
                    await asyncio.sleep(1)  # Brief pause before retry
                    continue

                if not entries:
                    continue

                await self._process_entries(entries)
        except asyncio.CancelledError:
            logger.info("Embedding worker %s cancelled", self.consumer_name)
            raise

    async def _process_entries(
        self,
        entries: list[tuple[str, Sequence[tuple[str, dict[str, str]]]]],
    ) -> None:
        """Process a batch of stream entries."""
        ack_ids: list[str] = []

        for _stream, messages in entries:
            for message_id, data in messages:
                payload = data.get("payload")
                if payload is None:
                    logger.warning("Missing payload for entry %s", message_id)
                    ack_ids.append(message_id)
                    continue

                try:
                    job = EmbeddingJob.model_validate_json(payload)
                    await self._handle_job(job)
                    ack_ids.append(message_id)
                except Exception as exc:
                    logger.exception("Failed to process job %s", message_id)
                    try:
                        await self.dlq_manager.send_to_dlq(message_id, payload, exc)
                    except Exception as dlq_exc:
                        logger.error(
                            "Failed to send job %s to DLQ: %s", message_id, dlq_exc
                        )
                    ack_ids.append(message_id)

        # Acknowledge processed messages
        try:
            await self.redis_service.acknowledge_messages(ack_ids)
            await self.redis_service.delete_messages(ack_ids)
        except Exception as ack_exc:
            logger.error("Failed to ack/delete messages %s: %s", ack_ids, ack_exc)

    async def _handle_job(self, job: EmbeddingJob) -> None:
        """Handle a single embedding job."""
        if job.op == "delete":
            await self._delete_embedding(job)
            return

        # Create embedding
        vector = await self.encoder.embed(job.embed_text)
        await self.qdrant_service.ensure_collection(len(vector))

        # Build payload and store
        payload = self._build_payload(job)
        point_id = self._point_id(job)
        await self.qdrant_service.upsert_point(point_id, vector, payload)

        logger.info(
            "Embedding stored",
            extra={
                "product_id": payload.get("product_id"),
                "shop_id": payload.get("shop_id"),
            },
        )

    async def _delete_embedding(self, job: EmbeddingJob) -> None:
        """Delete an embedding from the vector store."""
        point_id = self._point_id(job)
        await self.qdrant_service.delete_point(point_id)

        logger.info(
            "Embedding deleted",
            extra={"product_id": job.product_id, "shop_id": job.shop_id},
        )

    @staticmethod
    def _point_id(job: EmbeddingJob) -> str:
        """Generate a deterministic point ID for the job."""
        name = f"{job.shop_id}:{job.product_id}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, name))

    @staticmethod
    def _build_payload(job: EmbeddingJob) -> dict:
        """Build the payload for storage."""
        payload = {
            "product_id": job.product_id,
            "shop_id": job.shop_id,
            "version": job.version,
            "trace_id": job.trace_id,
            "name": (
                job.metadata.get("name") if isinstance(job.metadata, dict) else None
            ),
            "description": (
                job.metadata.get("description")
                if isinstance(job.metadata, dict)
                else None
            ),
            "metadata": job.metadata,
        }
        return {k: v for k, v in payload.items() if v is not None}

    @staticmethod
    def _build_consumer_name() -> str:
        """Build a unique consumer name."""
        hostname = socket.gethostname()
        pid = os.getpid()
        suffix = uuid.uuid4().hex[:6]
        return f"{hostname}:{pid}:{suffix}"


def create_embedding_worker() -> EmbeddingWorker:
    """Factory function to create an embedding worker with all dependencies."""
    redis_service = create_redis_stream_service()
    qdrant_service = create_qdrant_service()
    dlq_manager = create_dlq_manager(redis_service)
    encoder = get_encoder_client()

    if encoder is None:
        raise RuntimeError(
            "Encoder client is not configured. Set OPENAI_API_KEY and "
            "OPENAI_EMBEDDING_MODEL.",
        )

    return EmbeddingWorker(
        redis_service=redis_service,
        qdrant_service=qdrant_service,
        dlq_manager=dlq_manager,
        encoder=encoder,
    )


async def run_worker(concurrency: int | None = None) -> None:
    """Run one or more embedding workers."""
    worker_count = concurrency or max(1, settings.WORKER_CONCURRENCY)
    workers = [create_embedding_worker() for _ in range(worker_count)]

    tasks = [asyncio.create_task(worker.run_forever()) for worker in workers]
    await asyncio.gather(*tasks, return_exceptions=True)


def main() -> None:
    """CLI entry point."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Embedding worker interrupted, shutting down")


if __name__ == "__main__":
    main()
