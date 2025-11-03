"""
FastAPI application entry point.
"""

from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import get_db

app = FastAPI(
    title="FastAPI Template",
    description="A production-ready FastAPI template",
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
async def health_check(db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Health check endpoint with database connectivity check.

    Args:
        db: Database session

    Returns:
        dict: Service health status
    """
    try:
        # Check database connectivity
        await db.execute(select(text("1")))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "healthy",
        "database": db_status,
        "environment": settings.ENVIRONMENT,
    }
