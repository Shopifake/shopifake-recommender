"""FastAPI application factory and bootstrap helpers."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.routes import include_api_routes
from src.config import settings

_UI_DIRECTORY = Path(__file__).resolve().parent / "ui"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="Shopifake Recommender",
        description="RAG-based product recommender service",
        version="1.0.0",
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
