"""Debug routes for manual decoder testing during development."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.config import settings
from src.services.decoder_client import DecoderDependency

router = APIRouter(prefix="/debug", tags=["debug"])


class DecoderRequest(BaseModel):
    prompt: str = Field(..., description="Prompt text sent to the decoder")


class DecoderResponse(BaseModel):
    output: str = Field(..., description="Decoder response text")


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
    return DecoderResponse(output=output)
