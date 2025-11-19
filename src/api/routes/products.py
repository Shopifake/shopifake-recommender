"""Routes for managing products within the recommender."""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.models.product import ProductPayload, RegisteredProduct
from src.services.product_registry import ProductRegistry, get_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["products"])

RegistryDependency = Annotated[ProductRegistry, Depends(get_registry)]


@router.post(
    "/register",
    response_model=RegisteredProduct,
    status_code=status.HTTP_201_CREATED,
    summary="Register or update a product inside the recommender",
)
async def register_product(
    payload: ProductPayload,
    registry: RegistryDependency,
) -> RegisteredProduct:
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
