"""Tests for the debug decoder endpoint."""

from __future__ import annotations

import pytest

from src.config import settings
from src.main import app
from src.services.decoder_client import get_decoder_client


@pytest.mark.asyncio
async def test_decoder_endpoint_returns_stubbed_output(client):
    payload = {"prompt": "Ping"}
    response = await client.post("/debug/decoder", json=payload)

    assert response.status_code == 200
    assert response.json()["output"] == "decoded::Ping"


@pytest.mark.asyncio
async def test_decoder_endpoint_reports_unavailable(client, decoder_stub):
    original_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = None
    app.dependency_overrides[get_decoder_client] = lambda: None

    response = await client.post("/debug/decoder", json={"prompt": "Ping"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Decoder is not configured in this environment"

    settings.OPENAI_API_KEY = original_key
    app.dependency_overrides.pop(get_decoder_client, None)
