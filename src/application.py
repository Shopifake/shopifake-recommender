"""FastAPI application factory and bootstrap helpers."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.routes import include_api_routes
from src.config import settings
from src.services.queue.embedding_queue import get_redis_client

_UI_DIRECTORY = Path(__file__).resolve().parent / "ui"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Handle application startup and shutdown events."""
    if not settings.is_production:
        # In development, don't clear Redis streams to avoid conflicts with worker
        logger = logging.getLogger(__name__)
        logger.info("Skipping Redis stream cleanup in development mode")
    else:
        # In production, clear Redis streams on startup
        logger = logging.getLogger(__name__)
        try:
            client = get_redis_client()
            # delete stream and dlq keys if present
            await client.delete(settings.EMBEDDINGS_STREAM_KEY)
            await client.delete(settings.DLQ_STREAM_KEY)
            # best-effort destroy consumer group if it exists
            try:
                await client.xgroup_destroy(
                    settings.EMBEDDINGS_STREAM_KEY,
                    settings.EMBEDDINGS_CONSUMER_GROUP,
                )
            except Exception:
                # ignore if group/stream doesn't exist
                logger.debug("No consumer group to destroy or xgroup_destroy failed")
            logger.info("Cleared embedding stream + DLQ for production startup")
        except Exception:
            logger.exception("Failed clearing prod Redis queue on startup")

    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="Shopifake Recommender",
        description="RAG-based product recommender service",
        version="1.0.0",
        lifespan=lifespan,
    )

    _configure_cors(app)
    _mount_ui(app)
    include_api_routes(app)

    return app


def _configure_cors(app: FastAPI) -> None:
    """Allow broad access in non-production environments."""

    if settings.is_production:
        return

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _mount_ui(app: FastAPI) -> None:
    """Serve the local testing UI when available and allowed."""

    if settings.is_production or not _UI_DIRECTORY.exists():
        return

    app.mount("/ui", StaticFiles(directory=_UI_DIRECTORY, html=True), name="ui")
