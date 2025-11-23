"""Decoder client abstractions and implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Annotated, Any

from fastapi import Depends
from openai import AsyncOpenAI

from src.config import settings


class DecoderClient(ABC):
    """Abstract decoder interface for text generation models."""

    @abstractmethod
    async def decode(self, prompt: str) -> str:
        """Return the decoded/completed text for the provided prompt."""


class OpenAIDecoderClient(DecoderClient):
    """Decoder implementation backed by OpenAI Responses API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required to initialize decoder client")
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self._model = model

    async def decode(self, prompt: str) -> str:
        """Send the prompt to OpenAI and return the aggregated text output."""

        responses_api = getattr(self._client, "responses", None)
        if responses_api is not None:
            return await self._decode_with_responses(responses_api, prompt)

        chat_api = getattr(getattr(self._client, "chat", None), "completions", None)
        if chat_api is not None:
            return await self._decode_with_chat_completions(chat_api, prompt)

        raise RuntimeError(
            "OpenAI client does not expose Responses or Chat Completions endpoints",
        )

    async def _decode_with_responses(self, responses_api: Any, prompt: str) -> str:
        response = await responses_api.create(
            model=self._model,
            input=prompt,
        )

        pieces: list[str] = []
        for block in response.output or []:
            if block.type == "output_text" and block.content:
                pieces.append("".join(part.text for part in block.content if part.text))

        return "".join(pieces) or str(response)

    async def _decode_with_chat_completions(
        self,
        chat_api: Any,
        prompt: str,
    ) -> str:
        completion = await chat_api.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )

        if getattr(completion, "choices", None):
            message = completion.choices[0].message
            content = getattr(message, "content", None)
            if isinstance(content, list):
                # Newer SDKs can return list-based content payloads
                text_chunks = (
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
                return "".join(text_chunks) or str(completion)
            if content:
                return content

        return str(completion)


_decoder_client: DecoderClient | None = None


def _initialize_decoder() -> DecoderClient | None:
    if not settings.OPENAI_API_KEY:
        return None
    return OpenAIDecoderClient(
        api_key=settings.OPENAI_API_KEY,
        model=settings.OPENAI_MODEL,
    )


_decoder_client = _initialize_decoder()


def get_decoder_client() -> DecoderClient | None:
    """FastAPI dependency to obtain the configured decoder client if available."""

    return _decoder_client


DecoderDependency = Annotated[DecoderClient | None, Depends(get_decoder_client)]
