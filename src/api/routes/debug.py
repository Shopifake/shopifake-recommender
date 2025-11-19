"""Debug routes for manual decoder testing during development."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.config import settings
from src.services.decoder_client import DecoderDependency
from src.services.encoder_client import EncoderDependency

router = APIRouter(prefix="/debug", tags=["debug"])
logger = logging.getLogger(__name__)


class DecoderRequest(BaseModel):
    prompt: str = Field(..., description="Prompt text sent to the decoder")


class DecoderResponse(BaseModel):
    output: str = Field(..., description="Decoder response text")


class EncoderRequest(BaseModel):
    text: str = Field(..., description="Text content to encode")


class EncoderResponse(BaseModel):
    vector: list[float] = Field(..., description="Embedding vector for the text")


@router.post(
    "/decoder",
    response_model=DecoderResponse,
    status_code=status.HTTP_200_OK,
    summary="Run a decoder completion for debugging",
)
async def run_decoder(
    payload: DecoderRequest,
    decoder: DecoderDependency,
) -> DecoderResponse:
    """Pass the prompt to the configured decoder and return its raw output."""

    if not settings.decoder_enabled or decoder is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Decoder is not configured in this environment",
        )

    output = await decoder.decode(payload.prompt)
    logger.info(
        "Decoder responded",
        extra={
            "prompt": payload.prompt,
            "output_preview": output[:200],
            "output_length": len(output),
        },
    )
    return DecoderResponse(output=output)


@router.post(
    "/encoder",
    response_model=EncoderResponse,
    status_code=status.HTTP_200_OK,
    summary="Run an encoder embedding for debugging",
)
async def run_encoder(
    payload: EncoderRequest,
    encoder: EncoderDependency,
) -> EncoderResponse:
    """Generate embeddings for the provided text using the configured encoder."""

    print("starting encoder")

    if not settings.encoder_enabled or encoder is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Encoder is not configured in this environment",
        )

    vector = await encoder.embed(payload.text)
    logger.info(
        "Encoder responded",
        extra={
            "text": payload.text,
            "vector_dimensions": len(vector),
            "vector_preview": vector[:5],
        },
    )
    return EncoderResponse(vector=vector)
