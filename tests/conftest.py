"""Pytest configuration and fixtures for the recommender service."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.services.product_registry import ProductRegistry, get_registry


@pytest.fixture()
def registry() -> ProductRegistry:
    """Provide a fresh in-memory registry and wire it into the app."""

    instance = ProductRegistry()
    app.dependency_overrides[get_registry] = lambda: instance
    yield instance
    app.dependency_overrides.clear()


@pytest.fixture()
async def client(registry: ProductRegistry):
    """Return an HTTPX async client pointing at the FastAPI app."""

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client
