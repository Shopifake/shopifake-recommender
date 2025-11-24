"""Tests for the embedding ingestion endpoint."""

import asyncio

import pytest  # type: ignore[import]
from redis.exceptions import RedisError  # type: ignore[import]

from src.main import app
from src.services.queue.embedding_queue import get_embedding_queue


class _StubQueue:
    def __init__(self) -> None:
        self.batches: list[list[dict]] = []

    async def enqueue(self, jobs):
        await asyncio.sleep(0)
        serialized = [
            job.model_dump() if hasattr(job, "model_dump") else job for job in jobs
        ]
        self.batches.append(serialized)
        return len(serialized)


class _FailingQueue:
    async def enqueue(self, jobs):  # noqa: ARG002 - required signature
        await asyncio.sleep(0)
        raise RedisError("redis offline")


@pytest.fixture()
def queue_override():
    queue = _StubQueue()
    app.dependency_overrides[get_embedding_queue] = lambda: queue
    yield queue
    app.dependency_overrides.pop(get_embedding_queue, None)


@pytest.fixture()
def failing_queue_override():
    app.dependency_overrides[get_embedding_queue] = lambda: _FailingQueue()
    yield
    app.dependency_overrides.pop(get_embedding_queue, None)


@pytest.mark.asyncio
async def test_enqueue_embeddings_success(client, queue_override):
    payload = {
        "items": [
            {
                "product_id": "prod-1",
                "shop_id": "shop-A",
                "embed_text": "A cozy reading lamp",
                "metadata": {"price": 199.0},
                "op": "create",
                "version": 10,
                "trace_id": "trace-123",
            },
            {
                "product_id": "prod-2",
                "shop_id": "shop-A",
                "embed_text": "Minimalist sconce",
                "metadata": {},
                "op": "update",
            },
        ],
    }

    response = await client.post("/v1/embeddings", json=payload)

    assert response.status_code == 202
    assert response.json()["queued"] == 2
    assert len(queue_override.batches) == 1
    assert queue_override.batches[0][0]["product_id"] == "prod-1"


@pytest.mark.asyncio
async def test_enqueue_embeddings_queue_failure(client, failing_queue_override):
    payload = {
        "items": [
            {
                "product_id": "prod-x",
                "shop_id": "shop-z",
                "embed_text": "Something",
            }
        ]
    }

    response = await client.post("/v1/embeddings", json=payload)

    assert response.status_code == 503
    assert response.json()["detail"] == "Embedding queue unavailable"
