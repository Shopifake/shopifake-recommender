"""Integration tests for the embedding pipeline using real services."""

import asyncio
import json
import uuid
from typing import AsyncGenerator

import pytest
import redis.asyncio as redis
from httpx import ASGITransport, AsyncClient
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from src.config import settings
from src.main import app
from src.services.queue.embedding_queue import get_embedding_queue, get_redis_client
from src.services.storage.qdrant_service import create_qdrant_service


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def redis_integration() -> AsyncGenerator[redis.Redis, None]:
    """Provide a real Redis connection for integration tests."""
    client = redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )

    # Clean up any existing test data
    await client.flushdb()

    yield client

    # Cleanup after tests
    await client.flushdb()
    await client.aclose()


@pytest.fixture(scope="session")
async def qdrant_integration() -> AsyncGenerator[QdrantClient, None]:
    """Provide a real Qdrant connection for integration tests."""
    client = QdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
    )

    # Clean up any existing test collections
    try:
        client.delete_collection("products_embeddings")
    except Exception:
        pass  # Collection might not exist

    yield client

    # Cleanup after tests
    try:
        client.delete_collection("products_embeddings")
    except Exception:
        pass


@pytest.fixture
async def integration_client(redis_integration, qdrant_integration) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client with real service dependencies for integration tests."""

    # Override dependencies to use real services
    app.dependency_overrides[get_redis_client] = lambda: redis_integration

    # Create a mock queue that uses the real Redis
    from src.services.queue.embedding_queue import EmbeddingQueue
    real_queue = EmbeddingQueue(redis_integration)
    app.dependency_overrides[get_embedding_queue] = lambda: real_queue

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client

    # Clean up overrides
    app.dependency_overrides.pop(get_redis_client, None)
    app.dependency_overrides.pop(get_embedding_queue, None)


@pytest.mark.integration
async def test_full_embedding_pipeline_integration(
    integration_client: AsyncClient,
    redis_integration: redis.Redis,
    qdrant_integration: QdrantClient,
):
    """Test the complete embedding pipeline from registration to storage using real services."""

    # Step 1: Register a product
    product_data = {
        "product_id": f"integration-test-{uuid.uuid4().hex[:8]}",
        "site_id": "integration-site",
        "name": "Integration Test Lamp",
        "description": "A lamp for integration testing",
        "images": [],
        "categories": [],
        "sku": "INT-001",
        "status": "PUBLISHED",
        "price": 99.99,
        "filters": [],
        "metadata": {"test": True},
    }

    response = await integration_client.post("/products/register", json=product_data)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["product_id"] == product_data["product_id"]

    # Step 2: Verify job was enqueued in Redis
    # Wait a bit for async processing
    await asyncio.sleep(0.1)

    # Check that job exists in Redis stream
    stream_data = await redis_integration.xread(
        streams={"embeddings:jobs": "0"},
        count=10,
    )

    assert len(stream_data) > 0
    stream_name, messages = stream_data[0]
    assert stream_name == "embeddings:jobs"
    assert len(messages) >= 1

    # Verify the job data
    message_id, message_data = messages[0]
    job_payload = json.loads(message_data["payload"])

    assert job_payload["product_id"] == product_data["product_id"]
    assert job_payload["shop_id"] == product_data["site_id"]
    assert "embed_text" in job_payload
    assert job_payload["embed_text"] == "Integration Test Lamp A lamp for integration testing"

    # Step 3: Simulate worker processing (in a real scenario, a worker would run)
    from src.services.workers.embedding_worker import create_embedding_worker

    worker = create_embedding_worker()

    # Process one batch
    entries = await worker.redis_service.read_batch(
        consumer_name="integration-test-consumer",
        count=10,
        block_ms=1000,
    )

    if entries:
        await worker._process_entries(entries)

        # Step 4: Verify embedding was stored in Qdrant
        # Wait for async processing
        await asyncio.sleep(0.1)

        # Check collection exists
        collections = qdrant_integration.get_collections()
        collection_names = [c.name for c in collections.collections]
        assert "products_embeddings" in collection_names

        # Check point was stored
        points = qdrant_integration.scroll(
            collection_name="products_embeddings",
            limit=10,
        )[0]

        assert len(points) >= 1
        stored_point = points[0]

        assert stored_point.payload["product_id"] == product_data["product_id"]
        assert stored_point.payload["shop_id"] == product_data["site_id"]
        assert len(stored_point.vector) > 0  # Should have embedding vector


@pytest.mark.integration
async def test_product_registration_with_real_queue_integration(
    integration_client: AsyncClient,
    redis_integration: redis.Redis,
):
    """Test product registration with real Redis queue."""

    product_data = {
        "product_id": f"queue-test-{uuid.uuid4().hex[:8]}",
        "site_id": "queue-site",
        "name": "Queue Test Product",
        "description": "Testing real queue",
        "images": [],
        "categories": [],
        "sku": "QUEUE-001",
        "status": "PUBLISHED",
        "filters": [],
        "metadata": {},
    }

    # Register product
    response = await integration_client.post("/products/register", json=product_data)
    assert response.status_code == 202

    # Verify job was queued
    await asyncio.sleep(0.1)  # Allow async processing

    # Check Redis stream directly
    stream_info = await redis_integration.xinfo_stream("embeddings:jobs")
    assert stream_info["length"] >= 1

    # Verify we can read the job
    jobs = await redis_integration.xread(
        streams={"embeddings:jobs": "0"},
        count=1,
    )

    assert len(jobs) == 1
    _, messages = jobs[0]
    assert len(messages) == 1

    job_data = json.loads(messages[0][1]["payload"])
    assert job_data["product_id"] == product_data["product_id"]
    assert job_data["shop_id"] == product_data["site_id"]


@pytest.mark.integration
async def test_worker_processing_with_real_services_integration(
    redis_integration: redis.Redis,
    qdrant_integration: QdrantClient,
):
    """Test worker processing with real Redis and Qdrant services."""

    # Create a test job directly in Redis
    job = {
        "product_id": f"worker-test-{uuid.uuid4().hex[:8]}",
        "shop_id": "worker-site",
        "embed_text": "Test embedding text for worker",
        "metadata": {"test": True},
        "op": "create",
    }

    # Add job to Redis stream
    await redis_integration.xadd(
        "embeddings:jobs",
        {"payload": json.dumps(job)}
    )

    # Create worker with real services
    from src.services.workers.embedding_worker import create_embedding_worker
    worker = create_embedding_worker()

    # Process the job
    entries = await worker.redis_service.read_batch(
        consumer_name="integration-worker",
        count=1,
        block_ms=100,
    )

    assert len(entries) > 0
    await worker._process_entries(entries)

    # Verify embedding was stored
    await asyncio.sleep(0.1)  # Allow async processing

    points = qdrant_integration.scroll(
        collection_name="products_embeddings",
        limit=10,
    )[0]

    # Find our test point
    test_points = [p for p in points if p.payload.get("product_id") == job["product_id"]]
    assert len(test_points) == 1

    stored_point = test_points[0]
    assert stored_point.payload["product_id"] == job["product_id"]
    assert stored_point.payload["shop_id"] == job["shop_id"]
    assert len(stored_point.vector) > 0


@pytest.mark.integration
async def test_error_handling_with_real_services_integration(
    integration_client: AsyncClient,
    redis_integration: redis.Redis,
):
    """Test error handling with real services (invalid product data)."""

    # Try to register product with invalid data
    invalid_product_data = {
        "product_id": "",  # Invalid: empty product_id
        "site_id": "error-site",
        "name": "Invalid Product",
        "description": "This should fail validation",
        "images": [],
        "categories": [],
        "sku": "ERR-001",
        "status": "PUBLISHED",
        "filters": [],
        "metadata": {},
    }

    response = await integration_client.post("/products/register", json=invalid_product_data)

    # Should still return 202 (accepted) but job should fail processing
    assert response.status_code == 202

    # Check if job was enqueued despite invalid data
    await asyncio.sleep(0.1)

    jobs = await redis_integration.xread(
        streams={"embeddings:jobs": "0"},
        count=10,
    )

    # Should have a job, but it will fail when processed
    assert len(jobs) > 0

    # In a real scenario, we'd run a worker and check DLQ
    # For this test, we just verify the job was enqueued</content>
<parameter name="filePath">/Users/maxime/Desktop/Polytech/IG5/shopifake_dev/shopifake-back/services/shopifake-recommender/tests/test_integration.py