"""In-memory registry used to demo product registrations."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from threading import RLock

from src.models.product import ProductPayload, RegisteredProduct

logger = logging.getLogger(__name__)


class ProductRegistry:
    """Naive in-memory product registry for demo purposes."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._storage: dict[str, RegisteredProduct] = {}

    def register(self, payload: ProductPayload) -> RegisteredProduct:
        """Register a product and log the payload for observability."""

        registered = RegisteredProduct(**payload.model_dump())
        with self._lock:
            self._storage[payload.product_id] = registered

        logger.info(
            "Registered product %s for site %s", payload.product_id, payload.site_id
        )
        logger.debug("Product payload: %s", registered.model_dump_json())
        return registered

    def list_products(self) -> Iterable[RegisteredProduct]:
        with self._lock:
            return list(self._storage.values())


_registry = ProductRegistry()


def get_registry() -> ProductRegistry:
    """FastAPI dependency factory."""

    return _registry
