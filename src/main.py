"""
FastAPI application entry point.
"""

from fastapi import FastAPI

from src.config import settings

app = FastAPI(
    title="Shopifake Recommender",
    description="RAG-based product recommender service",
    version="1.0.0",
)


@app.get("/")
async def read_root():
    """
    Hello World endpoint.

    Returns:
        dict: A simple greeting message
    """
    return {"message": "Hello World"}


@app.get("/health")
async def health_check():
    """
    Health check endpoint with Qdrant connectivity check.

    Returns:
        dict: Service health status
    """
    import httpx

    qdrant_url = settings.QDRANT_URL or "http://qdrant:6333"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{qdrant_url}/collections", timeout=5.0)
            qdrant_status = (
                "connected" if response.status_code == 200 else "disconnected"
            )
    except Exception:
        qdrant_status = "disconnected"

    return {
        "status": "healthy",
        "qdrant": qdrant_status,
        "environment": settings.ENVIRONMENT,
    }
