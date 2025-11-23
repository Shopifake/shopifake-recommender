"""FastAPI application entry point."""

from src.application import create_app

app = create_app()

__all__ = ["app"]
