"""System-level routes such as health checks."""

from __future__ import annotations

import httpx
from fastapi import APIRouter

from src.config import settings

router = APIRouter(tags=["system"])


@router.get("/")
async def read_root() -> dict[str, str]:
    """Hello World endpoint used by smoke tests."""

    return {"message": "Hello World"}


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint with Qdrant connectivity check."""

    qdrant_url = settings.QDRANT_URL or "http://qdrant:6333"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{qdrant_url}/collections", timeout=5.0)
            qdrant_status = (
                "connected" if response.status_code == 200 else "disconnected"
            )
    except Exception:
        qdrant_status = "disconnected"

    return {
        "status": "healthy",
        "qdrant": qdrant_status,
        "environment": settings.ENVIRONMENT,
    }
