"""API route registration."""

from fastapi import FastAPI

from src.api.routes import chat, debug, embeddings, faq, products, rag, system


def include_api_routes(app: FastAPI) -> None:
    """Attach all API routers to the application."""

    app.include_router(system.router)
    app.include_router(products.router)
    app.include_router(debug.router)
    app.include_router(embeddings.router)
    app.include_router(rag.router)
    app.include_router(chat.router)
    app.include_router(faq.router)
