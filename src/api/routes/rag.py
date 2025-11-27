"""Routes that expose the queued RAG search workflow."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Path, status

from src.config import settings
from src.models.rag import (
    RAGSearchEnqueueResponse,
    RAGSearchJob,
    RAGSearchRequest,
    RAGSearchResultEnvelope,
)
from src.services.queue.embedding_queue import get_redis_client
from src.services.rag.result_store import RAGResultStore

router = APIRouter(prefix="/v1/rag", tags=["rag"])


@router.post(
    "/search",
    response_model=RAGSearchEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a queued RAG search",
)
async def enqueue_search(payload: RAGSearchRequest) -> RAGSearchEnqueueResponse:
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query text cannot be empty")

    top_k = payload.top_k or settings.RAG_DEFAULT_TOP_K
    top_k = min(top_k, settings.RAG_MAX_TOP_K)

    request_id = str(uuid.uuid4())
    job = RAGSearchJob(
        request_id=request_id,
        query=payload.query.strip(),
        top_k=top_k,
        score_threshold=payload.score_threshold,
    )

    client = get_redis_client()
    store = RAGResultStore(client)
    await store.initialize(request_id)

    await client.xadd(
        settings.RAG_QUERY_STREAM_KEY,
        fields={"payload": job.model_dump_json()},
        id="*",
    )

    return RAGSearchEnqueueResponse(request_id=request_id)


@router.get(
    "/search/{request_id}",
    response_model=RAGSearchResultEnvelope,
    summary="Poll the status/results of a queued RAG search",
)
async def fetch_search_result(
    request_id: str = Path(
        ...,
        description="Identifier returned by the queue endpoint",
    ),
) -> RAGSearchResultEnvelope:
    client = get_redis_client()
    store = RAGResultStore(client)
    data = await store.fetch(request_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Unknown request id")

    # Ensure response schema validation
    return RAGSearchResultEnvelope(**data)
