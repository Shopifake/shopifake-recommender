"""Qdrant vector database service for embedding storage."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from qdrant_client import QdrantClient  # type: ignore[import]
from qdrant_client.http import models as qmodels  # type: ignore[import]

from src.config import settings

logger = logging.getLogger(__name__)


class QdrantService:
    """Service for managing Qdrant vector database operations."""

    def __init__(self, client: QdrantClient, collection_name: str):
        self.client = client
        self.collection_name = collection_name
        self._collection_ready = False

    async def ensure_collection(self, vector_size: int) -> None:
        """Ensure the collection exists with the correct configuration. Always checks Qdrant."""
        try:
            await asyncio.to_thread(
                self.client.get_collection,
                collection_name=self.collection_name,
            )
            self._collection_ready = True
            return
        except Exception:
            logger.info("Creating Qdrant collection %s", self.collection_name)

        await asyncio.to_thread(
            self.client.create_collection,
            collection_name=self.collection_name,
            vectors_config=qmodels.VectorParams(
                size=vector_size,
                distance=qmodels.Distance.COSINE,
            ),
        )
        self._collection_ready = True

    async def upsert_point(
        self, point_id: str, vector: list[float], payload: dict[str, Any]
    ) -> None:
        """Upsert a point into the collection, recreating collection if missing."""
        point = qmodels.PointStruct(
            id=point_id,
            vector=vector,
            payload=payload,
        )
        try:
            await asyncio.to_thread(
                self.client.upsert,
                collection_name=self.collection_name,
                points=[point],
            )
        except Exception as exc:
            # If collection is missing, recreate and retry once
            if "doesn't exist" in str(exc) or "Not found" in str(exc):
                logger.warning("Qdrant collection missing, recreating: %s", self.collection_name)
                self._collection_ready = False
                await self.ensure_collection(len(vector))
                await asyncio.to_thread(
                    self.client.upsert,
                    collection_name=self.collection_name,
                    points=[point],
                )
            else:
                raise

    async def upsert_point(
        self, point_id: str, vector: list[float], payload: dict[str, Any]
    ) -> None:
        """Upsert a point into the collection."""
        point = qmodels.PointStruct(
            id=point_id,
            vector=vector,
            payload=payload,
        )
        await asyncio.to_thread(
            self.client.upsert,
            collection_name=self.collection_name,
            points=[point],
        )

    async def delete_point(self, point_id: str) -> None:
        """Delete a point from the collection."""
        await asyncio.to_thread(
            self.client.delete,
            collection_name=self.collection_name,
            points_selector=qmodels.PointIdsList(points=[point_id]),
        )

    async def search_similar(
        self,
        query_vector: list[float],
        limit: int = 10,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar vectors."""
        search_result = await asyncio.to_thread(
            self.client.search,
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
        )

        return [
            {
                "id": hit.id,
                "score": hit.score,
                "payload": hit.payload,
            }
            for hit in search_result
        ]


def create_qdrant_service(collection_name: str | None = None) -> QdrantService:
    """Factory function to create a Qdrant service."""
    client = QdrantClient(url=settings.QDRANT_URL)
    collection = collection_name or settings.QDRANT_COLLECTION
    return QdrantService(client, collection)
