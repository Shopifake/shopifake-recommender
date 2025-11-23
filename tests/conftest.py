"""Pytest configuration and fixtures for the recommender service."""

import asyncio

import pytest
import pytest_asyncio
import redis.asyncio as redis
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.services.clients.decoder_client import get_decoder_client
from src.services.clients.encoder_client import get_encoder_client
from src.services.queue.embedding_queue import get_redis_client


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line("markers", "asyncio: marks tests as async tests")


@pytest.fixture(autouse=True)
def decoder_stub():
    """Provide a stub decoder so tests do not call external services."""
    from src.main import app

    class _StubDecoder:
        async def decode(self, prompt: str) -> str:
            await asyncio.sleep(0)
            return f"decoded::{prompt}"

    stub = _StubDecoder()
    original_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = original_key or "test-key"
    app.dependency_overrides[get_decoder_client] = lambda: stub
    yield stub
    app.dependency_overrides.pop(get_decoder_client, None)
    settings.OPENAI_API_KEY = original_key


@pytest.fixture(autouse=True)
def encoder_stub():
    """Provide a stub encoder for tests to avoid API calls."""
    from src.main import app

    class _StubEncoder:
        async def embed(self, text: str) -> list[float]:
            await asyncio.sleep(0)
            return [1.0, float(len(text))]

    stub = _StubEncoder()
    original_model = settings.OPENAI_EMBEDDING_MODEL
    settings.OPENAI_EMBEDDING_MODEL = original_model or "test-embedding"
    app.dependency_overrides[get_encoder_client] = lambda: stub
    yield stub
    app.dependency_overrides.pop(get_encoder_client, None)
    settings.OPENAI_EMBEDDING_MODEL = original_model


@pytest.fixture()
def redis_client():
    """Provide a fresh Redis client for each test."""
    from src.main import app

    client = redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    # Override the global Redis client for this test
    app.dependency_overrides[get_redis_client] = lambda: client
    yield client
    app.dependency_overrides.pop(get_redis_client, None)


@pytest_asyncio.fixture()
async def client(redis_client):
    """Return an HTTPX async client pointing at the FastAPI app."""
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client
