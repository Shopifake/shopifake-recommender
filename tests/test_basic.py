"""
Basic tests for FastAPI application.
"""

import pytest


@pytest.mark.asyncio
async def test_read_root(client):
    """
    Test the root endpoint returns Hello World.
    """
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}


@pytest.mark.asyncio
async def test_health_check(client):
    """
    Test the health check endpoint returns healthy status with database check.
    """
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "qdrant" in data
    assert data["qdrant"] in ["connected", "disconnected"]
    assert "environment" in data
