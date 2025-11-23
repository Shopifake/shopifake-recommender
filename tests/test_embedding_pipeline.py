"""Comprehensive tests for the embedding pipeline from registration to storage."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from src.main import app
from src.services.queue.dlq_manager import DLQManager
from src.services.queue.embedding_queue import get_embedding_queue, get_redis_client
from src.services.queue.redis_stream import RedisStreamService
from src.services.storage.qdrant_service import QdrantService
from src.services.workers.embedding_worker import EmbeddingWorker


def create_mock_worker_services(mock_encoder):
    """Create mock services for testing the embedding worker."""
    # Mock Redis service
    mock_redis_service = MagicMock(spec=RedisStreamService)
    mock_redis_service.ensure_consumer_group = AsyncMock()
    mock_redis_service.read_batch = AsyncMock(return_value=[])
    mock_redis_service.acknowledge_messages = AsyncMock()
    mock_redis_service.delete_messages = AsyncMock()
    mock_redis_service.stream_key = "embeddings:jobs"
    mock_redis_service.group_name = "workers"
    mock_redis_service.consumer_name = "test-consumer"

    # Mock Qdrant service
    mock_qdrant_service = MagicMock(spec=QdrantService)
    mock_qdrant_service.ensure_collection = AsyncMock()
    mock_qdrant_service.upsert_point = AsyncMock()
    mock_qdrant_service.delete_point = AsyncMock()

    # Mock DLQ manager
    mock_dlq_manager = MagicMock(spec=DLQManager)
    mock_dlq_manager.send_to_dlq = AsyncMock()

    return mock_redis_service, mock_qdrant_service, mock_dlq_manager


class _MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        self.stream_data = {}
        self.consumer_groups = {}

    def xadd(self, stream=None, fields=None, name=None, **kwargs):
        # Handle both positional and keyword arguments
        stream_name = stream or name
        if stream_name not in self.stream_data:
            self.stream_data[stream_name] = []
        entry_id = kwargs.get("id", "*")
        if entry_id == "*":
            # Generate a simple ID
            entry_id = f"{len(self.stream_data[stream_name]):010d}-0"
        self.stream_data[stream_name].append((entry_id, fields))
        return entry_id

    async def xreadgroup(self, groupname, consumername, streams, count=1, block=None):
        stream_key = list(streams.keys())[0]
        self.consumer_groups.setdefault(stream_key, {})
        self.consumer_groups[stream_key].setdefault(
            groupname, {"consumers": {}, "pending": []}
        )
        group_data = self.consumer_groups[stream_key][groupname]
        group_data["consumers"].setdefault(consumername, {"pending": []})
        consumer_data = group_data["consumers"][consumername]

        if consumer_data["pending"]:
            entries = consumer_data["pending"][:count]
            consumer_data["pending"] = consumer_data["pending"][count:]
            return [(stream_key, entries)]

        def is_new_entry(entry_id):
            return not any(
                entry_id in str(pending) for pending in group_data["pending"]
            )

        if stream_key in self.stream_data:
            new_entries = [
                (entry_id, fields)
                for entry_id, fields in self.stream_data[stream_key]
                if is_new_entry(entry_id)
            ]
            for entry in new_entries[:count]:
                consumer_data["pending"].append(entry)
            if new_entries:
                return [(stream_key, new_entries[:count])]

        if block:
            await asyncio.sleep(0.01)
        return []

    def xgroup_create(self, name, groupname, id="0", mkstream=True):
        if name not in self.consumer_groups:
            self.consumer_groups[name] = {}
        if groupname not in self.consumer_groups[name]:
            self.consumer_groups[name][groupname] = {"consumers": {}, "pending": []}
        return "OK"

    def ping(self):
        return True

    async def close(self):
        # Method intentionally left empty: mock resource cleanup not needed
        pass

    async def aclose(self):
        # Method intentionally left empty: mock resource cleanup not needed
        pass

    def xack(self, stream, group, *message_ids):
        # Mock acknowledgment - just return OK
        return "OK"

    def xdel(self, stream, *message_ids):
        # Mock deletion - just return the count
        return len(message_ids)


class _MockQdrantClient:
    """Mock Qdrant client for testing."""

    def __init__(self):
        self.collections = {}
        self.points = {}

    def create_collection(self, collection_name, **kwargs):
        self.collections[collection_name] = {
            "vectors": kwargs.get("vectors_config", {})
        }

    def upsert(self, collection_name, points, **kwargs):
        if collection_name not in self.points:
            self.points[collection_name] = {}
        for point in points:
            self.points[collection_name][str(point.id)] = {
                "vector": point.vector,
                "payload": point.payload,
            }

    def delete(self, collection_name, points_selector, **kwargs):
        # Simple mock implementation - just record the call
        pass

    def scroll(self, collection_name, limit=100, **kwargs):
        if collection_name not in self.points:
            return [], None
        points = list(self.points[collection_name].values())[:limit]
        # Convert back to point-like objects
        result_points = []
        for i, point_data in enumerate(points):
            mock_point = MagicMock()
            mock_point.id = list(self.points[collection_name].keys())[i]
            mock_point.vector = point_data["vector"]
            mock_point.payload = point_data["payload"]
            result_points.append(mock_point)
        return result_points, None


@pytest.fixture()
def mock_redis():
    """Mock Redis client."""
    return _MockRedis()


@pytest.fixture()
def mock_qdrant():
    """Mock Qdrant client."""
    client = _MockQdrantClient()
    client.create_collection("products_embeddings")
    # Make delete a mock so we can assert on it
    client.delete = MagicMock()
    # Keep upsert as the original implementation but make it a mock for assertions
    original_upsert = client.upsert
    client.upsert = MagicMock(side_effect=original_upsert)
    return client


@pytest.fixture()
def mock_encoder():
    """Mock encoder client."""
    mock = MagicMock()
    mock.embed = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4, 0.5] * 153)  # 765 dims
    return mock


@pytest_asyncio.fixture()
async def queue_override(mock_redis):
    """Override the embedding queue with mock Redis."""
    app.dependency_overrides[get_redis_client] = lambda: mock_redis
    app.dependency_overrides[get_embedding_queue] = lambda: MagicMock(
        enqueue=AsyncMock(return_value=1)
    )
    yield mock_redis
    app.dependency_overrides.pop(get_redis_client, None)
    app.dependency_overrides.pop(get_embedding_queue, None)


@pytest.mark.asyncio
async def test_product_registration_enqueues_embedding(client, queue_override):
    """Test that product registration automatically enqueues an embedding job."""
    payload = {
        "product_id": "prod-test-1",
        "site_id": "site-test",
        "name": "Test Lamp",
        "description": "A test lamp for embedding",
        "images": ["https://example.com/lamp.jpg"],
        "categories": [{"id": "cat-1", "site_id": "site-test", "name": "Lighting"}],
        "sku": "TEST-001",
        "status": "PUBLISHED",
        "price": 99.99,
        "filters": [],
        "metadata": {"color": "white"},
    }

    # Mock the queue enqueue method to capture calls
    mock_queue = MagicMock()
    mock_queue.enqueue = AsyncMock(return_value=1)
    app.dependency_overrides[get_embedding_queue] = lambda: mock_queue

    try:
        response = await client.post("/products/register", json=payload)

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["product_id"] == payload["product_id"]

        # Verify embedding job was enqueued
        mock_queue.enqueue.assert_called_once()
        call_args = mock_queue.enqueue.call_args[0][0]  # First positional arg
        assert len(call_args) == 1
        job = call_args[0]
        assert job.product_id == "prod-test-1"
        assert job.shop_id == "site-test"
        assert job.embed_text == "Test Lamp A test lamp for embedding"
        assert abs(job.metadata["price"] - 99.99) < 0.01
    finally:
        app.dependency_overrides.pop(get_embedding_queue, None)


@pytest.mark.asyncio
async def test_product_registration_handles_enqueue_failure(client):
    """Test that product registration succeeds even if embedding enqueue fails."""
    payload = {
        "product_id": "prod-test-2",
        "site_id": "site-test",
        "name": "Test Lamp",
        "description": "A test lamp",
        "images": [],
        "categories": [],
        "sku": "TEST-002",
        "status": "PUBLISHED",
        "filters": [],
        "metadata": {},
    }

    # Mock queue that raises an exception
    mock_queue = MagicMock()
    mock_queue.enqueue = AsyncMock(side_effect=Exception("Queue unavailable"))
    app.dependency_overrides[get_embedding_queue] = lambda: mock_queue

    try:
        response = await client.post("/products/register", json=payload)

        # Registration should still succeed despite enqueue failure
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["product_id"] == payload["product_id"]

        # Verify enqueue was attempted
        mock_queue.enqueue.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_embedding_queue, None)


@pytest.mark.asyncio
async def test_worker_processes_embedding_job(mock_redis, mock_qdrant, mock_encoder):
    """Test that the embedding worker processes jobs and stores in Qdrant."""
    # Create mock services
    mock_redis_service, mock_qdrant_service, mock_dlq_manager = (
        create_mock_worker_services(mock_encoder)
    )

    # Create a worker with mock services
    worker = EmbeddingWorker(
        redis_service=mock_redis_service,
        qdrant_service=mock_qdrant_service,
        dlq_manager=mock_dlq_manager,
        encoder=mock_encoder,
    )

    # Create a proper EmbeddingJob
    from src.models.embedding import EmbeddingJob

    job = EmbeddingJob(
        product_id="prod-worker-test",
        shop_id="site-worker",
        embed_text="Test product for worker",
        metadata={"price": 49.99},
    )

    # Mock the read_batch to return the job
    entries = [("embeddings:jobs", [("123-0", {"payload": job.model_dump_json()})])]
    mock_redis_service.read_batch.return_value = entries

    # Process the entries
    await worker._process_entries(entries)

    # Verify the services were called correctly
    mock_encoder.embed.assert_called_once_with("Test product for worker")
    mock_qdrant_service.ensure_collection.assert_called_once()
    mock_qdrant_service.upsert_point.assert_called_once()
    mock_redis_service.acknowledge_messages.assert_called_once_with(["123-0"])
    mock_redis_service.delete_messages.assert_called_once_with(["123-0"])


@pytest.mark.asyncio
async def test_worker_handles_encoder_failure(mock_redis, mock_qdrant):
    """Test that worker handles encoder failures gracefully."""
    # Mock encoder that fails
    mock_encoder = MagicMock()
    mock_encoder.embed = AsyncMock(side_effect=Exception("OpenAI API error"))

    # Create mock services
    mock_redis_service, mock_qdrant_service, mock_dlq_manager = (
        create_mock_worker_services(mock_encoder)
    )

    worker = EmbeddingWorker(
        redis_service=mock_redis_service,
        qdrant_service=mock_qdrant_service,
        dlq_manager=mock_dlq_manager,
        encoder=mock_encoder,
    )

    # Create a job that will fail
    from src.models.embedding import EmbeddingJob

    job = EmbeddingJob(
        product_id="prod-fail-test",
        shop_id="site-fail",
        embed_text="This will fail",
        metadata={},
    )

    # Mock the read_batch to return the job
    entries = [("embeddings:jobs", [("123-0", {"payload": job.model_dump_json()})])]
    mock_redis_service.read_batch.return_value = entries

    # Process the entries
    await worker._process_entries(entries)

    # Verify DLQ was called due to encoder failure
    mock_dlq_manager.send_to_dlq.assert_called_once()
    # Verify no successful embedding was stored
    mock_qdrant_service.upsert_point.assert_not_called()


@pytest.mark.asyncio
async def test_worker_handles_qdrant_failure(mock_redis):
    """Test that worker handles Qdrant storage failures."""
    # Mock encoder that succeeds
    encoder = MagicMock()
    encoder.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])

    # Create mock services with failing Qdrant
    mock_redis_service, mock_qdrant_service, mock_dlq_manager = (
        create_mock_worker_services(mock_encoder)
    )
    mock_qdrant_service.upsert_point = AsyncMock(
        side_effect=Exception("Qdrant connection error")
    )

    worker = EmbeddingWorker(
        redis_service=mock_redis_service,
        qdrant_service=mock_qdrant_service,
        dlq_manager=mock_dlq_manager,
        encoder=mock_encoder,
    )

    # Create a job
    from src.models.embedding import EmbeddingJob

    job = EmbeddingJob(
        product_id="prod-qdrant-fail",
        shop_id="site-qdrant",
        embed_text="Qdrant will fail",
        metadata={},
    )

    # Mock the read_batch to return the job
    entries = [("embeddings:jobs", [("123-0", {"payload": job.model_dump_json()})])]
    mock_redis_service.read_batch.return_value = entries

    # Process the entries
    await worker._process_entries(entries)

    # Verify Qdrant upsert was attempted but failed, and DLQ was called
    mock_qdrant_service.upsert_point.assert_called_once()
    mock_dlq_manager.send_to_dlq.assert_called_once()


@pytest.mark.asyncio
async def test_worker_handles_malformed_json(mock_redis, mock_qdrant, mock_encoder):
    """Test that worker handles malformed JSON payloads gracefully."""
    # Create mock services
    mock_redis_service, mock_qdrant_service, mock_dlq_manager = (
        create_mock_worker_services(mock_encoder)
    )

    worker = EmbeddingWorker(
        redis_service=mock_redis_service,
        qdrant_service=mock_qdrant_service,
        dlq_manager=mock_dlq_manager,
        encoder=mock_encoder,
    )

    # Mock malformed JSON entry
    entries = [("embeddings:jobs", [("123-0", {"payload": "{invalid json"})])]
    mock_redis_service.read_batch.return_value = entries

    # Process the entries
    await worker._process_entries(entries)

    # Verify DLQ was called for malformed JSON
    mock_dlq_manager.send_to_dlq.assert_called_once()


@pytest.mark.asyncio
async def test_worker_handles_missing_payload(mock_redis, mock_qdrant, mock_encoder):
    """Test that worker handles messages without payload field."""
    # Create mock services
    mock_redis_service, mock_qdrant_service, mock_dlq_manager = (
        create_mock_worker_services(mock_encoder)
    )

    worker = EmbeddingWorker(
        redis_service=mock_redis_service,
        qdrant_service=mock_qdrant_service,
        dlq_manager=mock_dlq_manager,
        encoder=mock_encoder,
    )

    # Add message without payload
    await mock_redis.xadd("embeddings:jobs", {"other_field": "value"})

    # Mock the read_batch to return the message without payload
    entries = [("embeddings:jobs", [("123-0", {"other_field": "value"})])]
    mock_redis_service.read_batch.return_value = entries

    # Process the job
    await worker._process_entries(entries)

    # Verify no DLQ entries (message is just acked and ignored)
    mock_dlq_manager.send_to_dlq.assert_not_called()
    mock_redis_service.acknowledge_messages.assert_called_once_with(["123-0"])
    mock_redis_service.delete_messages.assert_called_once_with(["123-0"])


@pytest.mark.asyncio
async def test_worker_handles_empty_embed_text(mock_redis, mock_qdrant, mock_encoder):
    """Test that worker handles empty embed_text."""
    # Create mock services
    mock_redis_service, mock_qdrant_service, mock_dlq_manager = (
        create_mock_worker_services(mock_encoder)
    )

    worker = EmbeddingWorker(
        redis_service=mock_redis_service,
        qdrant_service=mock_qdrant_service,
        dlq_manager=mock_dlq_manager,
        encoder=mock_encoder,
    )

    # Add job with empty embed_text - this should fail validation and go to DLQ
    job_data = {
        "product_id": "prod-empty-text",
        "shop_id": "site-empty",
        "embed_text": "",
        "metadata": {},
    }
    payload = json.dumps(job_data)
    await mock_redis.xadd("embeddings:jobs", {"payload": payload})

    # Mock the read_batch to return the job
    entries = [("embeddings:jobs", [("123-0", {"payload": payload})])]
    mock_redis_service.read_batch.return_value = entries

    # Process the job
    await worker._process_entries(entries)

    # Verify job was sent to DLQ due to validation error
    mock_dlq_manager.send_to_dlq.assert_called_once()
    mock_redis_service.acknowledge_messages.assert_called_once_with(["123-0"])
    mock_redis_service.delete_messages.assert_called_once_with(["123-0"])


@pytest.mark.asyncio
async def test_worker_handles_delete_operation(mock_redis, mock_qdrant, mock_encoder):
    """Test that worker handles delete operations correctly."""
    # Create mock services
    mock_redis_service, mock_qdrant_service, mock_dlq_manager = (
        create_mock_worker_services(mock_encoder)
    )

    worker = EmbeddingWorker(
        redis_service=mock_redis_service,
        qdrant_service=mock_qdrant_service,
        dlq_manager=mock_dlq_manager,
        encoder=mock_encoder,
    )

    # Add delete job
    job_data = {
        "product_id": "prod-delete",
        "shop_id": "site-delete",
        "embed_text": "This won't be embedded",
        "op": "delete",
        "metadata": {},
    }
    payload = json.dumps(job_data)
    await mock_redis.xadd("embeddings:jobs", {"payload": payload})

    # Mock the read_batch to return the job
    entries = [("embeddings:jobs", [("123-0", {"payload": payload})])]
    mock_redis_service.read_batch.return_value = entries

    # Process the job
    await worker._process_entries(entries)

    # Verify delete was called on Qdrant
    mock_qdrant_service.delete_point.assert_called_once()
    mock_encoder.embed.assert_not_called()  # Should not embed for delete
    mock_redis_service.acknowledge_messages.assert_called_once_with(["123-0"])
    mock_redis_service.delete_messages.assert_called_once_with(["123-0"])


@pytest.mark.asyncio
async def test_worker_handles_invalid_job_data(mock_redis, mock_qdrant, mock_encoder):
    """Test that worker handles invalid EmbeddingJob data."""
    # Create mock services
    mock_redis_service, mock_qdrant_service, mock_dlq_manager = (
        create_mock_worker_services(mock_encoder)
    )

    worker = EmbeddingWorker(
        redis_service=mock_redis_service,
        qdrant_service=mock_qdrant_service,
        dlq_manager=mock_dlq_manager,
        encoder=mock_encoder,
    )

    # Add job with missing required fields
    job_data = {
        "shop_id": "site-invalid",
        "embed_text": "Missing product_id",
        "metadata": {},
    }
    payload = json.dumps(job_data)
    await mock_redis.xadd("embeddings:jobs", {"payload": payload})

    # Mock the read_batch to return the job
    entries = [("embeddings:jobs", [("123-0", {"payload": payload})])]
    mock_redis_service.read_batch.return_value = entries

    # Process the job
    await worker._process_entries(entries)

    # Verify job was sent to DLQ due to validation error
    mock_dlq_manager.send_to_dlq.assert_called_once()
    mock_redis_service.acknowledge_messages.assert_called_once_with(["123-0"])
    mock_redis_service.delete_messages.assert_called_once_with(["123-0"])


@pytest.mark.asyncio
async def test_worker_handles_dlq_failure(mock_redis, mock_qdrant):
    """Test that worker handles DLQ failures gracefully."""
    # Mock encoder that fails
    mock_encoder = MagicMock()
    mock_encoder.embed = AsyncMock(side_effect=Exception("Encoder error"))

    # Create mock services
    mock_redis_service, mock_qdrant_service, mock_dlq_manager = (
        create_mock_worker_services(mock_encoder)
    )

    # Mock DLQ manager to fail
    mock_dlq_manager.send_to_dlq = AsyncMock(side_effect=Exception("DLQ write failed"))

    worker = EmbeddingWorker(
        redis_service=mock_redis_service,
        qdrant_service=mock_qdrant_service,
        dlq_manager=mock_dlq_manager,
        encoder=mock_encoder,
    )

    # Add a job
    job_data = {
        "product_id": "prod-dlq-fail",
        "shop_id": "site-dlq-fail",
        "embed_text": "This will fail and DLQ will fail",
        "metadata": {},
    }
    payload = json.dumps(job_data)

    # Mock the read_batch to return the job
    entries = [("embeddings:jobs", [("123-0", {"payload": payload})])]
    mock_redis_service.read_batch.return_value = entries

    # Process the job - this should handle the DLQ failure gracefully
    await worker._process_entries(entries)

    # Verify that processing completed despite DLQ failure
    # (The job failed but was still acked)
    mock_dlq_manager.send_to_dlq.assert_called_once()
    mock_redis_service.acknowledge_messages.assert_called_once_with(["123-0"])
    mock_redis_service.delete_messages.assert_called_once_with(["123-0"])


@pytest.mark.asyncio
async def test_worker_handles_redis_ack_failure(mock_redis, mock_qdrant, mock_encoder):
    """Test that worker handles Redis ack failures gracefully."""
    # Create mock services
    mock_redis_service, mock_qdrant_service, mock_dlq_manager = (
        create_mock_worker_services(mock_encoder)
    )

    # Mock acknowledge_messages to fail
    mock_redis_service.acknowledge_messages = AsyncMock(
        side_effect=Exception("Ack failed")
    )

    worker = EmbeddingWorker(
        redis_service=mock_redis_service,
        qdrant_service=mock_qdrant_service,
        dlq_manager=mock_dlq_manager,
        encoder=mock_encoder,
    )

    # Add a job
    job_data = {
        "product_id": "prod-ack-fail",
        "shop_id": "site-ack-fail",
        "embed_text": "Ack will fail",
        "metadata": {},
    }
    payload = json.dumps(job_data)

    # Mock the read_batch to return the job
    entries = [("embeddings:jobs", [("123-0", {"payload": payload})])]
    mock_redis_service.read_batch.return_value = entries

    # Process the job - this should handle ack failure gracefully
    await worker._process_entries(entries)

    # Verify job was still processed (stored in Qdrant) despite ack failure
    mock_encoder.embed.assert_called_once()
    mock_qdrant_service.ensure_collection.assert_called_once()
    mock_qdrant_service.upsert_point.assert_called_once()
    mock_redis_service.acknowledge_messages.assert_called_once_with(["123-0"])
    # delete_messages should not be called if ack fails
    mock_redis_service.delete_messages.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_end_to_end(client, mock_redis, mock_qdrant, mock_encoder):
    """Test the complete pipeline from registration to storage."""
    # Override dependencies
    mock_queue = MagicMock()
    enqueue_calls = []
    mock_queue.enqueue = AsyncMock(
        side_effect=lambda jobs: enqueue_calls.append(jobs) or len(jobs)
    )

    app.dependency_overrides[get_redis_client] = lambda: mock_redis
    app.dependency_overrides[get_embedding_queue] = lambda: mock_queue

    try:
        # Step 1: Register product
        payload = {
            "product_id": "prod-e2e-1",
            "site_id": "site-e2e",
            "name": "End-to-End Lamp",
            "description": "Complete pipeline test",
            "images": [],
            "categories": [],
            "sku": "E2E-001",
            "status": "PUBLISHED",
            "price": 79.99,
            "filters": [],
            "metadata": {"test": True},
        }

        response = await client.post("/products/register", json=payload)
        assert response.status_code == 202

        # Step 2: Verify job was enqueued
        assert len(enqueue_calls) == 1
        jobs = enqueue_calls[0]
        assert len(jobs) == 1
        job = jobs[0]
        assert job.product_id == "prod-e2e-1"
        assert job.embed_text == "End-to-End Lamp Complete pipeline test"

        # Step 3: Simulate worker processing
        # Create mock services
        mock_redis_service, mock_qdrant_service, mock_dlq_manager = (
            create_mock_worker_services(mock_encoder)
        )

        worker = EmbeddingWorker(
            redis_service=mock_redis_service,
            qdrant_service=mock_qdrant_service,
            dlq_manager=mock_dlq_manager,
            encoder=mock_encoder,
        )

        # Manually add the job to Redis (simulating what the queue does)
        job_dict = {
            "product_id": job.product_id,
            "shop_id": job.shop_id,
            "embed_text": job.embed_text,
            "metadata": job.metadata,
        }
        await mock_redis.xadd("embeddings:jobs", {"payload": json.dumps(job_dict)})

        # Mock the read_batch to return the job
        entries = [("embeddings:jobs", [("123-0", {"payload": json.dumps(job_dict)})])]
        mock_redis_service.read_batch.return_value = entries

        # Process the job
        await worker._process_entries(entries)

        # Step 4: Verify embedding was stored
        mock_encoder.embed.assert_called_once_with(
            "End-to-End Lamp Complete pipeline test"
        )
        mock_qdrant_service.ensure_collection.assert_called_once()
        mock_qdrant_service.upsert_point.assert_called_once()
        mock_redis_service.acknowledge_messages.assert_called_once_with(["123-0"])
        mock_redis_service.delete_messages.assert_called_once_with(["123-0"])

    finally:
        app.dependency_overrides.pop(get_redis_client, None)
        app.dependency_overrides.pop(get_embedding_queue, None)
