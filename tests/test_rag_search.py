"""Tests covering the queued RAG search API and worker helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.config import settings
from src.models.rag import RAGSearchJob
from src.services.queue.redis_stream import RedisStreamService
from src.services.rag.result_store import RAGResultStore
from src.services.workers.rag_worker import RAGSearchWorker


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_rag_worker_handles_job_and_persists_results():
    redis_service = MagicMock(spec=RedisStreamService)
    redis_service.stream_key = settings.RAG_QUERY_STREAM_KEY
    redis_service.group_name = settings.RAG_QUERY_CONSUMER_GROUP

    result_store = AsyncMock(spec=RAGResultStore)
    encoder = AsyncMock()
    encoder.embed.return_value = [0.1, 0.2]

    qdrant_service = AsyncMock()
    qdrant_service.search_similar.return_value = [
        {
            "score": 0.95,
            "payload": {
                "product_id": "prod-1",
                "shop_id": "site-1",
                "description": "A fancy lamp",
                "metadata": {"price": 42},
            },
        }
    ]

    worker = RAGSearchWorker(
        redis_service=redis_service,
        qdrant_service=qdrant_service,
        result_store=result_store,
        encoder=encoder,
    )

    job = RAGSearchJob(request_id="req-123", query="lamp", top_k=3)
    await worker._handle_job(job)

    result_store.save_success.assert_awaited_once()
    args, _ = result_store.save_success.await_args
    assert args[0] == "req-123"
    assert args[1][0]["product_id"] == "prod-1"
    assert args[1][0]["description"] == "A fancy lamp"
