"""Worker responsible for processing queued RAG search requests."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from collections.abc import Sequence

from src.config import settings
from src.models.rag import RAGSearchJob
from src.services.clients.encoder_client import EncoderClient, get_encoder_client
from src.services.queue.redis_stream import (
    RedisStreamService,
    create_redis_stream_service,
)
from src.services.rag.result_store import RAGResultStore
from src.services.storage.qdrant_service import QdrantService, create_qdrant_service
from src.services.workers.base import BaseWorker

logger = logging.getLogger(__name__)


class RAGSearchWorker(BaseWorker):
    """Consumes RAG search jobs from Redis, runs similarity search, stores results."""

    def __init__(
        self,
        *,
        redis_service: RedisStreamService,
        qdrant_service: QdrantService,
        result_store: RAGResultStore,
        encoder: EncoderClient,
        consumer_name: str | None = None,
    ) -> None:
        super().__init__(consumer_name)
        self.redis_service = redis_service
        self.qdrant_service = qdrant_service
        self.result_store = result_store
        self.encoder = encoder
        self.batch_size = settings.BATCH_MAX_MESSAGES
        self.block_ms = settings.BATCH_MAX_WAIT_MS

    async def run_forever(self) -> None:
        await self.redis_service.ensure_consumer_group()
        logger.info(
            "RAG worker started",
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
                    logger.error("Failed to read RAG queue: %s", exc, exc_info=True)
                    await asyncio.sleep(1)
                    continue

                if not entries:
                    continue

                await self._process_entries(entries)
        except asyncio.CancelledError:
            logger.info("RAG worker %s cancelled", self.consumer_name)
            raise

    async def _process_entries(
        self,
        entries: list[tuple[str, Sequence[tuple[str, dict[str, str]]]]],
    ) -> None:
        ack_ids: list[str] = []

        for _stream, messages in entries:
            for message_id, data in messages:
                payload = data.get("payload")
                if payload is None:
                    logger.warning("RAG job missing payload: %s", message_id)
                    ack_ids.append(message_id)
                    continue

                try:
                    job = RAGSearchJob.model_validate_json(payload)
                except Exception as exc:
                    logger.error("Invalid RAG job payload: %s", exc, exc_info=True)
                    ack_ids.append(message_id)
                    continue

                await self.result_store.mark_processing(job.request_id)
                try:
                    await self._handle_job(job)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    # Requirement: if OpenAI/encoder fails, log to terminal and continue
                    logger.exception("RAG job %s failed", job.request_id)
                    await self.result_store.save_failure(job.request_id, str(exc))
                finally:
                    ack_ids.append(message_id)

        try:
            await self.redis_service.acknowledge_messages(ack_ids)
            await self.redis_service.delete_messages(ack_ids)
        except Exception as exc:
            logger.error("Failed to ack/delete RAG messages: %s", exc, exc_info=True)

    async def _handle_job(self, job: RAGSearchJob) -> None:
        vector = await self.encoder.embed(job.query)
        results = await self.qdrant_service.search_similar(
            vector,
            limit=job.top_k,
            score_threshold=job.score_threshold,
        )

        formatted = [
            {
                "product_id": hit.get("payload", {}).get("product_id"),
                "shop_id": hit.get("payload", {}).get("shop_id"),
                "score": hit.get("score"),
                "description": hit.get("payload", {}).get("description"),
                "metadata": hit.get("payload", {}).get("metadata"),
            }
            for hit in results
        ]

        await self.result_store.save_success(job.request_id, formatted)

    @staticmethod
    def _build_consumer_name() -> str:
        hostname = socket.gethostname()
        pid = os.getpid()
        suffix = uuid.uuid4().hex[:6]
        return f"rag-worker:{hostname}:{pid}:{suffix}"


def create_rag_worker() -> RAGSearchWorker:
    redis_service = create_redis_stream_service(
        stream_key=settings.RAG_QUERY_STREAM_KEY,
        group_name=settings.RAG_QUERY_CONSUMER_GROUP,
    )
    qdrant_service = create_qdrant_service()
    encoder = get_encoder_client()
    if encoder is None:
        raise RuntimeError("Encoder client not configured for RAG worker")

    client = redis_service.client
    result_store = RAGResultStore(client)

    return RAGSearchWorker(
        redis_service=redis_service,
        qdrant_service=qdrant_service,
        result_store=result_store,
        encoder=encoder,
    )


async def run_worker(concurrency: int | None = None) -> None:
    worker_count = concurrency or 1
    workers = [create_rag_worker() for _ in range(worker_count)]
    tasks = [asyncio.create_task(worker.run_forever()) for worker in workers]
    await asyncio.gather(*tasks, return_exceptions=True)


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("RAG worker interrupted, exiting")


if __name__ == "__main__":
    main()
