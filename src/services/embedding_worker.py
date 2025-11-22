"""Redis consumer responsible for processing embedding jobs."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from collections.abc import Sequence

import redis.asyncio as redis  # type: ignore[import]
from qdrant_client import QdrantClient  # type: ignore[import]
from qdrant_client.http import models as qmodels  # type: ignore[import]
from redis.exceptions import RedisError, ResponseError  # type: ignore[import]

from src.config import settings
from src.models.embedding import EmbeddingJob
from src.services.encoder_client import EncoderClient, get_encoder_client

logger = logging.getLogger(__name__)


class EmbeddingWorker:
    """Consumes jobs from Redis Streams and syncs them into Qdrant."""

    def __init__(
        self,
        *,
        redis_client: redis.Redis,
        encoder: EncoderClient,
        qdrant_client: QdrantClient,
        consumer_name: str | None = None,
    ) -> None:
        self.redis = redis_client
        self.encoder = encoder
        self.qdrant = qdrant_client
        self.stream_key = settings.EMBEDDINGS_STREAM_KEY
        self.group = settings.EMBEDDINGS_CONSUMER_GROUP
        self.dlq_stream = settings.DLQ_STREAM_KEY
        self.batch_size = settings.BATCH_MAX_MESSAGES
        self.block_ms = settings.BATCH_MAX_WAIT_MS
        self.consumer_name = consumer_name or self._build_consumer_name()
        self.collection = settings.QDRANT_COLLECTION
        self._collection_ready = False
        self._redis_backoff = 1
        self._max_backoff = 30

    async def run_forever(self) -> None:
        await self._ensure_consumer_group()
        logger.info(
            "Embedding worker started",
            extra={
                "stream": self.stream_key,
                "group": self.group,
                "consumer": self.consumer_name,
            },
        )

        try:
            while True:
                try:
                    entries = await self._read_batch()
                except RedisError as exc:  # pragma: no cover - best-effort logging
                    await self._handle_redis_disconnect(exc)
                    continue

                if not entries:
                    continue

                await self._process_entries(entries)
        except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
            logger.info("Embedding worker %s cancelled", self.consumer_name)
            raise

    async def _ensure_consumer_group(self) -> None:
        try:
            await self.redis.xgroup_create(
                name=self.stream_key,
                groupname=self.group,
                id="0",
                mkstream=True,
            )
            logger.info("Created Redis consumer group", extra={"group": self.group})
        except ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                logger.debug(
                    "Consumer group already exists", extra={"group": self.group}
                )
                return
            logger.error("Failed to create consumer group: %s", exc, exc_info=True)
            raise

    async def _read_batch(self):
        # Ensure group exists before reading
        await self._ensure_consumer_group()
        try:
            return await self.redis.xreadgroup(
                groupname=self.group,
                consumername=self.consumer_name,
                streams={self.stream_key: ">"},
                count=self.batch_size,
                block=self.block_ms,
            )
        except ResponseError as exc:
            if "NOGROUP" in str(exc):
                logger.warning("Consumer group still missing after ensure: %s", exc)
                # Try once more
                await self._ensure_consumer_group()
                return await self.redis.xreadgroup(
                    groupname=self.group,
                    consumername=self.consumer_name,
                    streams={self.stream_key: ">"},
                    count=self.batch_size,
                    block=self.block_ms,
                )
            raise

    async def _handle_redis_disconnect(self, exc: Exception) -> None:
        logger.error("Failed to read from Redis stream: %s", exc, exc_info=True)
        await self._close_redis_client()
        await self._reconnect_with_backoff()

    async def _close_redis_client(self) -> None:
        try:
            await self.redis.aclose()
        except Exception:
            logger.debug("Error closing redis client", exc_info=True)

    async def _reconnect_with_backoff(self) -> None:
        backoff = self._redis_backoff
        while True:
            try:
                self.redis = self._create_redis_client()
                await self.redis.ping()
                await self._ensure_consumer_group()
                logger.info(
                    "Re-established Redis connection",
                    extra={"consumer": self.consumer_name},
                )
                self._redis_backoff = 1
                return
            except Exception as reconnect_exc:
                logger.warning(
                    "Redis reconnect attempt failed (retrying)",
                    exc_info=reconnect_exc,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff)
                self._redis_backoff = backoff

    def _create_redis_client(self) -> redis.Redis:
        return _create_redis_client()

    async def _process_entries(
        self,
        entries: list[tuple[str, Sequence[tuple[str, dict[str, str]]]]],
    ) -> None:
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
                except Exception as exc:  # pragma: no cover - error path
                    logger.exception("Failed to process job %s", message_id)
                    try:
                        await self._send_to_dlq(message_id, payload, exc)
                    except Exception as dlq_exc:  # pragma: no cover - best-effort DLQ
                        logger.error(
                            "Failed to send job %s to DLQ: %s", message_id, dlq_exc
                        )
                    ack_ids.append(message_id)

        if ack_ids:
            try:
                await self.redis.xack(self.stream_key, self.group, *ack_ids)
                await self.redis.xdel(self.stream_key, *ack_ids)
            except Exception as ack_exc:  # pragma: no cover - best-effort ack
                logger.error("Failed to ack/delete messages %s: %s", ack_ids, ack_exc)

    async def _handle_job(self, job: EmbeddingJob) -> None:
        if job.op == "delete":
            await self._delete_point(job)
            return

        vector = await self.encoder.embed(job.embed_text)
        await self._ensure_collection(len(vector))
        payload = self._build_payload(job)
        point = qmodels.PointStruct(
            id=self._point_id(job),
            vector=vector,
            payload=payload,
        )
        await asyncio.to_thread(
            self.qdrant.upsert,
            collection_name=self.collection,
            points=[point],
        )
        logger.info(
            "Embedding stored",
            extra={
                "product_id": payload.get("product_id"),
                "shop_id": payload.get("shop_id"),
            },
        )

    async def _delete_point(self, job: EmbeddingJob) -> None:
        await asyncio.to_thread(
            self.qdrant.delete,
            collection_name=self.collection,
            points_selector=qmodels.PointIdsList(points=[self._point_id(job)]),
        )
        logger.info(
            "Embedding deleted",
            extra={"product_id": job.product_id, "shop_id": job.shop_id},
        )

    async def _send_to_dlq(self, entry_id: str, payload: str, exc: Exception) -> None:
        await self.redis.xadd(
            name=self.dlq_stream,
            fields={
                "payload": payload,
                "error": str(exc),
                "entry_id": entry_id,
            },
        )

    async def _ensure_collection(self, vector_size: int) -> None:
        if self._collection_ready:
            return

        try:
            await asyncio.to_thread(
                self.qdrant.get_collection,
                collection_name=self.collection,
            )
            self._collection_ready = True
            return
        except Exception:
            logger.info("Creating Qdrant collection %s", self.collection)

        await asyncio.to_thread(
            self.qdrant.create_collection,
            collection_name=self.collection,
            vectors_config=qmodels.VectorParams(
                size=vector_size,
                distance=qmodels.Distance.COSINE,
            ),
        )
        self._collection_ready = True

    @staticmethod
    def _point_id(job: EmbeddingJob) -> str:
        """Return a deterministic UUID string for the given job.

        Qdrant requires point IDs to be either an unsigned integer or a UUID.
        To keep IDs stable and human-independent we derive a UUIDv5 from
        the shop and product identifiers.
        """

        name = f"{job.shop_id}:{job.product_id}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, name))

    @staticmethod
    def _build_payload(job: EmbeddingJob) -> dict:
        payload = {
            "product_id": job.product_id,
            "shop_id": job.shop_id,
            "version": job.version,
            "trace_id": job.trace_id,
            "metadata": job.metadata,
        }
        return {k: v for k, v in payload.items() if v is not None}

    @staticmethod
    def _build_consumer_name() -> str:
        hostname = socket.gethostname()
        pid = os.getpid()
        suffix = uuid.uuid4().hex[:6]
        return f"{hostname}:{pid}:{suffix}"


def _create_redis_client() -> redis.Redis:
    return redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        health_check_interval=30,
    )


def _build_worker() -> EmbeddingWorker:
    redis_client = _create_redis_client()
    encoder = get_encoder_client()
    if encoder is None:
        raise RuntimeError(
            "Encoder client is not configured. Set OPENAI_API_KEY and "
            "OPENAI_EMBEDDING_MODEL.",
        )
    qdrant_client = QdrantClient(url=settings.QDRANT_URL)
    return EmbeddingWorker(
        redis_client=redis_client,
        encoder=encoder,
        qdrant_client=qdrant_client,
    )


async def run_worker(concurrency: int | None = None) -> None:
    worker_count = concurrency or max(1, settings.WORKER_CONCURRENCY)
    tasks = []
    for _ in range(worker_count):
        worker = _build_worker()
        tasks.append(asyncio.create_task(worker.run_forever()))

    await asyncio.gather(*tasks)


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Embedding worker interrupted, shutting down")


if __name__ == "__main__":
    main()
