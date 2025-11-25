"""Routes implementing the conversational /chat API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from src.models.chat import ChatEnqueueResponse, ChatRequest, ChatResultEnvelope
from src.services.chat.orchestrator import ChatOrchestrator, create_chat_orchestrator
from src.services.chat.result_store import ChatResultStore
from src.services.clients.decoder_client import DecoderDependency
from src.services.clients.encoder_client import EncoderDependency
from src.services.queue.embedding_queue import get_redis_client

router = APIRouter(prefix="/chat", tags=["chat"])


def _get_result_store() -> ChatResultStore:
    client = get_redis_client()
    return ChatResultStore(client)


def _build_orchestrator(
    encoder: EncoderDependency,
    decoder: DecoderDependency,
    store: Annotated[ChatResultStore, Depends(_get_result_store)],
) -> ChatOrchestrator:
    return create_chat_orchestrator(
        encoder=encoder,
        decoder=decoder,
        result_store=store,
    )


ResultStoreDependency = Annotated[ChatResultStore, Depends(_get_result_store)]
OrchestratorDependency = Annotated[ChatOrchestrator, Depends(_build_orchestrator)]


@router.post(
    "",
    response_model=ChatEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a conversational chat request",
)
async def submit_chat(
    payload: ChatRequest,
    background_tasks: BackgroundTasks,
    orchestrator: OrchestratorDependency,
) -> ChatEnqueueResponse:
    request_id = str(uuid.uuid4())
    await orchestrator.initialize_request(request_id)
    background_tasks.add_task(orchestrator.process_request, request_id, payload)
    return ChatEnqueueResponse(request_id=request_id)


@router.get(
    "/result/{request_id}",
    response_model=ChatResultEnvelope,
    summary="Fetch the latest chat result",
)
async def fetch_chat_result(
    request_id: str,
    store: ResultStoreDependency,
) -> ChatResultEnvelope:
    data = await store.fetch(request_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Unknown request id")
    return data
