"""FastAPI application entry point."""

from __future__ import annotations

import json
import logging
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, status

from src.config import settings
from src.models.product import ProductPayload, RegisteredProduct
from src.services.product_registry import ProductRegistry, get_registry

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Shopifake Recommender",
    description="RAG-based product recommender service",
    version="1.0.0",
)


@app.get("/")
async def read_root():
    """
    Hello World endpoint.

    Returns:
        dict: A simple greeting message
    """
    return {"message": "Hello World"}


@app.get("/health")
async def health_check():
    """
    Health check endpoint with Qdrant connectivity check.

    Returns:
        dict: Service health status
    """
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


RegistryDependency = Annotated[ProductRegistry, Depends(get_registry)]


@app.post(
    "/products/register",
    response_model=RegisteredProduct,
    status_code=status.HTTP_201_CREATED,
    summary="Register or update a product inside the recommender",
)
async def register_product(
    payload: ProductPayload,
    registry: RegistryDependency,
):
    """Store the product payload in the registry and echo it back."""

    logger.info(
        "Catalog registration received for product %s (site=%s)",
        payload.product_id,
        payload.site_id,
    )
    logger.debug("Received payload: %s", payload.model_dump_json())

    registered = registry.register(payload)

    # For demo purposes we also print the payload so it is visible in container logs.
    print(  # noqa: T201 - intentional for demo logging
        "[product-registration]",
        json.dumps(registered.model_dump(mode="json")),
        flush=True,
    )

    return registered
