"""Tests for the debug encoder endpoint."""

from __future__ import annotations

import pytest

from src.config import settings
from src.main import app
from src.services.clients.encoder_client import get_encoder_client


@pytest.mark.asyncio
async def test_encoder_endpoint_returns_stubbed_vector(client):
    payload = {"text": "Shopifake"}
    response = await client.post("/debug/encoder", json=payload)

    assert response.status_code == 200
    assert response.json()["vector"] == [1.0, float(len("Shopifake"))]


@pytest.mark.asyncio
async def test_encoder_endpoint_reports_unavailable(client, encoder_stub):
    original_model = settings.OPENAI_EMBEDDING_MODEL
    settings.OPENAI_EMBEDDING_MODEL = None
    app.dependency_overrides[get_encoder_client] = lambda: None

    response = await client.post("/debug/encoder", json={"text": "Ping"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Encoder is not configured in this environment"

    settings.OPENAI_EMBEDDING_MODEL = original_model
    app.dependency_overrides.pop(get_encoder_client, None)
