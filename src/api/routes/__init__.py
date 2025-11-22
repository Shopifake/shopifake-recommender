"""API route registration."""

from fastapi import FastAPI

from src.api.routes import debug, embeddings, products, system


def include_api_routes(app: FastAPI) -> None:
    """Attach all API routers to the application."""

    app.include_router(system.router)
    app.include_router(products.router)
    app.include_router(debug.router)
    app.include_router(embeddings.router)
