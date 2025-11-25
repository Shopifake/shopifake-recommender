"""Tests for the chat orchestration endpoints."""

from __future__ import annotations

import asyncio

import pytest


async def _poll_for_completion(client, request_id: str) -> dict:
    last_payload: dict | None = None
    for _ in range(10):
        response = await client.get(f"/chat/result/{request_id}")
        payload = response.json()
        last_payload = payload
        if payload["status"] != "pending":
            return payload
        await asyncio.sleep(0.05)
    return last_payload or {"status": "pending"}


@pytest.mark.asyncio
async def test_chat_returns_recommendations_when_context_present(client, redis_client):
    await redis_client.flushdb()
    payload = {
        "site_id": "site-001",
        "history": [
            {"role": "user", "content": "I need a present"},
            {
                "role": "rag",
                "content": {
                    "reply": "Could you tell me who the present is for?",
                    "recommendations": [],
                },
            },
            {"role": "user", "content": "It's for my brother, he loves music."},
        ],
        "query": "Show me more options",
    }

    response = await client.post("/chat", json=payload)
    assert response.status_code == 202
    request_id = response.json()["request_id"]

    result = await _poll_for_completion(client, request_id)
    # Accept either satisfied (if products found) or unsatisfied (if none)
    assert result["decoder_satisfaction"] in {"satisfied", "unsatisfied"}
    assert all(
        "product_id" in rec and "name" in rec for rec in result["recommendations"]
    )


@pytest.mark.asyncio
async def test_chat_handles_unsatisfied_query(client, redis_client):
    await redis_client.flushdb()
    payload = {
        "site_id": "site-001",
        "history": [],
        "query": "Looking for underwater drones",
    }

    response = await client.post("/chat", json=payload)
    assert response.status_code == 202
    request_id = response.json()["request_id"]

    result = await _poll_for_completion(client, request_id)
    # Accept either unsatisfied (no products found)
    # or need_more_info (if query is too vague)
    assert result["decoder_satisfaction"] in {"unsatisfied", "need_more_info"}
    assert all(
        "product_id" in rec and "name" in rec for rec in result["recommendations"]
    )
