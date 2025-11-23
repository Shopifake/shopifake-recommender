"""Encoder client abstractions and implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Annotated

from fastapi import Depends
from openai import AsyncOpenAI

from src.config import settings


class EncoderClient(ABC):
    """Abstract encoder interface responsible for producing embeddings."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Return the embedding vector for the provided text."""


class OpenAIEncoderClient(EncoderClient):
    """Encoder implementation backed by OpenAI's embeddings API."""

    def __init__(self, *, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required to initialize encoder client")
        if not model:
            raise ValueError("OpenAI embedding model must be provided")

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=text,
        )

        if not response.data:
            raise RuntimeError("OpenAI embeddings response did not include vector data")

        vector = response.data[0].embedding
        return list(vector)


_encoder_client: EncoderClient | None = None


def _initialize_encoder() -> EncoderClient | None:
    if not settings.encoder_enabled:
        return None

    return OpenAIEncoderClient(
        api_key=settings.OPENAI_API_KEY,
        model=settings.OPENAI_EMBEDDING_MODEL,
    )


_encoder_client = _initialize_encoder()


def get_encoder_client() -> EncoderClient | None:
    """FastAPI dependency returning the configured encoder client if any."""

    return _encoder_client


EncoderDependency = Annotated[EncoderClient | None, Depends(get_encoder_client)]
