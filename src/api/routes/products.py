"""Routes for managing products within the recommender."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.models.embedding import EmbeddingJob
from src.models.product import ProductPayload
from src.services.queue.embedding_queue import EmbeddingQueue, get_embedding_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["products"])

QueueDependency = Annotated[EmbeddingQueue, Depends(get_embedding_queue)]


@router.post(
    "/register",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Register or update a product inside the recommender",
)
async def register_product(
    payload: ProductPayload,
    queue: QueueDependency,
) -> dict[str, str]:
    """Enqueue embedding job for the product."""

    logger.info(
        "Catalog registration received for product %s (site=%s)",
        payload.product_id,
        payload.site_id,
    )
    logger.debug("Received payload: %s", payload.model_dump_json())

    # Enqueue embedding job for the product
    embed_text = f"{payload.name} {payload.description}".strip()
    if not embed_text:
        embed_text = payload.name or "unnamed product"

    job = EmbeddingJob(
        product_id=payload.product_id,
        shop_id=payload.site_id,
        embed_text=embed_text,
        metadata={"price": getattr(payload, "price", None)},
    )

    try:
        await queue.enqueue([job])
        logger.info("Enqueued embedding job for product %s", payload.product_id)
    except Exception as exc:
        logger.warning(
            "Failed to enqueue embedding job for product %s, but registration continues: %s",
            payload.product_id,
            exc,
        )
        # Don't fail registration if embedding enqueue fails - product can still be registered

    logger.info(
        "[product-registration]",
        extra={
            "product_id": payload.product_id,
            "site_id": payload.site_id,
        },
    )

    return {"status": "accepted", "product_id": payload.product_id}
