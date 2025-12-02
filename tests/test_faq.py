"""Tests for the FAQ chatbot endpoint."""

from __future__ import annotations

import pytest

from src.config import settings
from src.main import app
from src.services.clients.decoder_client import get_decoder_client


@pytest.mark.asyncio
async def test_faq_answer_returns_response_with_empty_history(client):
    """Test that the FAQ endpoint returns an answer when history is empty."""
    # Arrange
    payload = {
        "message": "How do I create my store?",
        "conversation_history": [],
    }

    # Act
    response = await client.post("/faq/answer", json=payload)

    # Assert
    assert response.status_code == 200
    response_data = response.json()
    assert "answer" in response_data
    assert len(response_data["answer"]) > 0


@pytest.mark.asyncio
async def test_faq_answer_returns_response_with_conversation_history(client):
    """Test that the FAQ endpoint handles conversation history correctly."""
    # Arrange
    payload = {
        "message": "And how do I add products?",
        "conversation_history": [
            {"role": "user", "content": "How do I create my store?"},
            {
                "role": "assistant",
                "content": "To create your store, follow these steps...",
            },
        ],
    }

    # Act
    response = await client.post("/faq/answer", json=payload)

    # Assert
    assert response.status_code == 200
    response_data = response.json()
    assert "answer" in response_data


@pytest.mark.asyncio
async def test_faq_answer_rejects_empty_message(client):
    """Test that the FAQ endpoint rejects requests with empty messages."""
    # Arrange
    payload = {
        "message": "",
        "conversation_history": [],
    }

    # Act
    response = await client.post("/faq/answer", json=payload)

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_faq_answer_rejects_whitespace_only_message(client):
    """Test that the FAQ endpoint rejects messages containing only whitespace."""
    # Arrange
    payload = {
        "message": "   ",
        "conversation_history": [],
    }

    # Act
    response = await client.post("/faq/answer", json=payload)

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_faq_answer_handles_decoder_unavailable(client, decoder_stub):
    """Test that the FAQ endpoint returns 503 when decoder is not available."""
    # Arrange
    original_api_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = None
    app.dependency_overrides[get_decoder_client] = lambda: None

    payload = {
        "message": "How do I create my store?",
        "conversation_history": [],
    }

    # Act
    response = await client.post("/faq/answer", json=payload)

    # Assert
    assert response.status_code == 503
    response_data = response.json()
    assert response_data["detail"] == "Decoder is not configured in this environment"

    # Cleanup
    settings.OPENAI_API_KEY = original_api_key
    app.dependency_overrides.pop(get_decoder_client, None)


@pytest.mark.asyncio
async def test_faq_answer_includes_message_in_decoder_call(client):
    """Test that the user message is passed to the decoder."""
    # Arrange
    test_question = "What payment methods are supported?"
    payload = {
        "message": test_question,
        "conversation_history": [],
    }

    # Act
    response = await client.post("/faq/answer", json=payload)

    # Assert
    assert response.status_code == 200
    response_data = response.json()
    # The stub decoder returns "decoded::{prompt}", so the answer should contain
    # the original question somewhere in the decoded prompt
    assert test_question in response_data["answer"]


@pytest.mark.asyncio
async def test_faq_answer_validates_history_entry_format(client):
    """Test that the FAQ endpoint validates conversation history entry format."""
    # Arrange - invalid history entry missing required fields
    payload = {
        "message": "How do I add a product?",
        "conversation_history": [
            {"invalid_field": "This should fail validation"},
        ],
    }

    # Act
    response = await client.post("/faq/answer", json=payload)

    # Assert
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_faq_answer_accepts_user_role_in_history(client):
    """Test that history entries with 'user' role are accepted."""
    # Arrange
    payload = {
        "message": "Tell me more",
        "conversation_history": [
            {"role": "user", "content": "First question"},
        ],
    }

    # Act
    response = await client.post("/faq/answer", json=payload)

    # Assert
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_faq_answer_accepts_assistant_role_in_history(client):
    """Test that history entries with 'assistant' role are accepted."""
    # Arrange
    payload = {
        "message": "Another question",
        "conversation_history": [
            {"role": "user", "content": "First question"},
            {"role": "assistant", "content": "First answer"},
        ],
    }

    # Act
    response = await client.post("/faq/answer", json=payload)

    # Assert
    assert response.status_code == 200
