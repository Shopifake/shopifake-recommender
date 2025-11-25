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
    "/register/batch",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Register or update multiple products inside the recommender",
)
async def register_products_batch(
    payload: list[ProductPayload],
    queue: QueueDependency,
) -> dict:
    """Enqueue embedding jobs for multiple products."""
    jobs = []
    for prod in payload:
        # TODO add more complexity here to have better embeddings
        embed_text = f"{prod.name} {prod.description}".strip()
        if not embed_text:
            embed_text = prod.name or "unnamed product"
        jobs.append(
            EmbeddingJob(
                product_id=prod.product_id,
                shop_id=prod.site_id,
                embed_text=embed_text,
                metadata={
                    "name": prod.name,
                    "description": prod.description,
                    "price": getattr(prod, "price", None),
                    "sku": prod.sku,
                    "status": prod.status,
                    "filters": [f.model_dump() for f in prod.filters],
                    "categories": [c.model_dump() for c in prod.categories],
                    "images": prod.images,
                    "extra": prod.metadata,
                },
            )
        )
    try:
        await queue.enqueue(jobs)
        logger.info("Enqueued embedding jobs for %d products", len(jobs))
    except Exception as exc:
        logger.warning(
            "Failed to enqueue embedding jobs for batch, "
            "but registration continues: %s",
            exc,
        )
    return {
        "status": "accepted",
        "count": len(jobs),
        "product_ids": [p.product_id for p in payload],
    }


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
        metadata={
            "name": payload.name,
            "description": payload.description,
            "price": getattr(payload, "price", None),
            "sku": payload.sku,
            "status": payload.status,
            "filters": [f.model_dump() for f in payload.filters],
            "categories": [c.model_dump() for c in payload.categories],
            "images": payload.images,
            "extra": payload.metadata,
        },
    )

    try:
        await queue.enqueue([job])
        logger.info("Enqueued embedding job for product %s", payload.product_id)
    except Exception as exc:
        logger.warning(
            "Failed to enqueue embedding job for product %s, "
            "but registration continues: %s",
            payload.product_id,
            exc,
        )
        # Don't fail registration if embedding enqueue fails

    logger.info(
        "[product-registration]",
        extra={
            "product_id": payload.product_id,
            "site_id": payload.site_id,
        },
    )

    return {"status": "accepted", "product_id": payload.product_id}
