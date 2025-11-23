"""Routes responsible for ingesting embedding jobs."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from qdrant_client import QdrantClient  # type: ignore[import]
from redis.exceptions import ResponseError

from src.config import settings
from src.models.embedding import EmbeddingJob
from src.services.queue.embedding_queue import (
    EmbeddingQueue,
    get_embedding_queue,
    get_redis_client,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/embeddings", tags=["embeddings"])

QueueDependency = Annotated[EmbeddingQueue, Depends(get_embedding_queue)]


@router.post(
    "",
    summary="Enqueue embedding jobs for processing",
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_embeddings(
    payload: dict[str, Any], queue: QueueDependency
) -> dict[str, int]:
    """Enqueue embedding jobs for asynchronous processing.

    Accepts a batch of embedding jobs to be processed by the embedding worker.
    Each job should contain the necessary fields for embedding generation.
    """
    items = payload.get("items", [])
    if not items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request must contain 'items' array with embedding jobs",
        )

    # Convert items to EmbeddingJob objects
    jobs = []
    for item in items:
        try:
            job = EmbeddingJob(**item)
            jobs.append(job)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid embedding job format: {exc}",
            )

    # Enqueue the jobs
    try:
        queued = await queue.enqueue(jobs)
        return {"queued": queued}
    except Exception:
        logger.exception("Failed to enqueue embedding jobs")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding queue unavailable",
        )


@router.get(
    "/stream",
    summary="List recent entries from the embeddings stream",
)
async def list_stream_entries(count: int = Query(100, ge=1, le=1000)) -> list[dict]:
    """Return recent entries from the embeddings stream for debugging."""

    client = get_redis_client()
    try:
        entries = await client.xrange(
            settings.EMBEDDINGS_STREAM_KEY, min="-", max="+", count=count
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )

    results: list[dict] = []
    for entry_id, fields in entries:
        payload = fields.get("payload")
        parsed = None
        if payload:
            try:
                parsed = json.loads(payload)
            except Exception:
                parsed = payload

        results.append({"id": entry_id, "payload": parsed, "fields": fields})

    return results


@router.get(
    "/pending",
    summary="Show pending messages for the consumer group",
)
async def view_pending(count: int = Query(100, ge=1, le=1000)) -> dict:
    """Return pending entries (XPENDING) for the embeddings consumer group."""

    client = get_redis_client()
    try:
        pending = await _fetch_pending_entries(client, count)
        summary = await _fetch_pending_summary(client)
    except ResponseError as exc:
        logger.debug("XPENDING failed (likely missing group/stream): %s", exc)
        return {"pending": [], "summary": None}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )

    return {"pending": pending, "summary": summary}


@router.get(
    "/dlq",
    summary="Read recent dead-letter queue entries",
)
async def read_dlq(count: int = Query(100, ge=1, le=1000)) -> list[dict]:
    client = get_redis_client()
    try:
        entries = await client.xrange(
            settings.DLQ_STREAM_KEY, min="-", max="+", count=count
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )

    results: list[dict] = []
    for entry_id, fields in entries:
        payload = fields.get("payload")
        parsed = None
        if payload:
            try:
                parsed = json.loads(payload)
            except Exception:
                parsed = payload
        results.append({"id": entry_id, "payload": parsed, "fields": fields})

    return results


@router.get(
    "/list",
    summary="List embeddings stored in Qdrant",
)
async def list_embeddings(limit: int = Query(100, ge=1, le=1000)) -> list[dict]:
    """Return list of embeddings from Qdrant collection for debugging."""

    try:
        client = QdrantClient(url=settings.QDRANT_URL)
        response = client.scroll(
            collection_name=settings.QDRANT_COLLECTION,
            limit=limit,
            with_payload=True,
            with_vectors=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )

    results: list[dict] = []
    points, _ = response
    for point in points:
        vector_slice = point.vector[:5] if point.vector else []
        results.append(
            {
                "id": str(point.id),
                "payload": point.payload,
                "vector_preview": vector_slice,
            }
        )

    return results


async def _fetch_pending_entries(client, count: int) -> list[dict[str, Any]]:
    """Return detailed pending entries when supported by the Redis client."""

    entries: list[dict[str, Any]] = []

    xpending_range = getattr(client, "xpending_range", None)
    if callable(xpending_range):
        try:
            rows = await xpending_range(
                settings.EMBEDDINGS_STREAM_KEY,
                settings.EMBEDDINGS_CONSUMER_GROUP,
                min="-",
                max="+",
                count=count,
            )
            return _format_pending_rows(rows)
        except ResponseError:
            raise
        except Exception as exc:
            logger.debug("xpending_range unavailable, falling back: %s", exc)

    try:
        rows = await client.xpending(
            settings.EMBEDDINGS_STREAM_KEY,
            settings.EMBEDDINGS_CONSUMER_GROUP,
            "-",
            "+",
            count,
        )
        entries = _format_pending_rows(rows)
    except TypeError:
        logger.debug("Redis client XPENDING implementation supports summary only")
    except AttributeError:
        logger.debug("Redis client missing xpending method")

    return entries


async def _fetch_pending_summary(client) -> dict[str, Any] | None:
    try:
        summary = await client.xpending(
            settings.EMBEDDINGS_STREAM_KEY,
            settings.EMBEDDINGS_CONSUMER_GROUP,
        )
    except ResponseError:
        raise
    except Exception as exc:
        logger.debug("Failed to load XPENDING summary: %s", exc)
        return None

    if not summary:
        return _build_summary_response(0, None, None, [])

    if hasattr(summary, "pending"):
        return _build_summary_response(
            getattr(summary, "pending", 0),
            getattr(summary, "min", None),
            getattr(summary, "max", None),
            getattr(summary, "consumers", []),
        )

    if isinstance(summary, dict):
        return _build_summary_response(
            summary.get("pending") or summary.get("count") or 0,
            summary.get("min") or summary.get("smallest"),
            summary.get("max") or summary.get("greatest"),
            summary.get("consumers", []),
        )

    try:
        total, smallest, greatest, consumers = summary
    except Exception:
        return {"raw": summary}

    return _build_summary_response(total, smallest, greatest, consumers)


def _format_pending_rows(rows: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not rows:
        return items

    for row in rows:
        parsed = _coerce_pending_row(row)
        if parsed is not None:
            items.append(parsed)
        else:
            items.append({"raw": row})

    return items


def _coerce_pending_row(row: Any) -> dict[str, Any] | None:
    if hasattr(row, "message_id"):
        return {
            "id": getattr(row, "message_id", None),
            "consumer": getattr(row, "consumer", None),
            "idle_ms": getattr(row, "idle", None),
            "deliveries": getattr(row, "times_delivered", None),
        }

    if isinstance(row, dict):
        if {"message_id", "consumer", "idle", "times_delivered"} <= row.keys():
            return {
                "id": row["message_id"],
                "consumer": row["consumer"],
                "idle_ms": row["idle"],
                "deliveries": row["times_delivered"],
            }
        if {"id", "consumer", "idle_ms", "deliveries"} <= row.keys():
            return {
                "id": row["id"],
                "consumer": row["consumer"],
                "idle_ms": row["idle_ms"],
                "deliveries": row["deliveries"],
            }

    if isinstance(row, (list, tuple)) and len(row) >= 4:
        msg_id, consumer, idle, deliveries = row[:4]
        return {
            "id": msg_id,
            "consumer": consumer,
            "idle_ms": idle,
            "deliveries": deliveries,
        }

    return None


def _build_summary_response(
    total: Any,
    smallest: Any,
    greatest: Any,
    consumers: Any,
) -> dict[str, Any]:
    return {
        "count": total,
        "smallest_id": smallest,
        "greatest_id": greatest,
        "consumers": _format_consumer_rows(consumers),
    }


def _format_consumer_rows(rows: Any) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    if not rows:
        return formatted

    for row in rows:
        parsed = _coerce_consumer_row(row)
        formatted.append(parsed if parsed is not None else {"raw": row})

    return formatted


def _coerce_consumer_row(row: Any) -> dict[str, Any] | None:
    if hasattr(row, "name"):
        return {
            "name": getattr(row, "name", None),
            "pending": getattr(row, "pending", None)
            or getattr(row, "count", None)
            or getattr(row, "pending_count", None),
        }

    if isinstance(row, dict):
        name = row.get("name") or row.get("consumer")
        pending = row.get("pending") or row.get("count") or row.get("pending_count")
        if name is not None or pending is not None:
            return {"name": name, "pending": pending}

    if isinstance(row, (list, tuple)) and len(row) >= 2:
        return {"name": row[0], "pending": row[1]}

    return None
