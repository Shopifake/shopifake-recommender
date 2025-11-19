"""Pytest configuration and fixtures for the recommender service."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.main import app
from src.services.decoder_client import get_decoder_client
from src.services.product_registry import ProductRegistry, get_registry


@pytest.fixture()
def registry() -> ProductRegistry:
    """Provide a fresh in-memory registry and wire it into the app."""

    instance = ProductRegistry()
    app.dependency_overrides[get_registry] = lambda: instance
    yield instance
    app.dependency_overrides.pop(get_registry, None)


@pytest.fixture(autouse=True)
def decoder_stub():
    """Provide a stub decoder so tests do not call external services."""

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


@pytest.fixture()
async def client(registry: ProductRegistry):
    """Return an HTTPX async client pointing at the FastAPI app."""

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client
