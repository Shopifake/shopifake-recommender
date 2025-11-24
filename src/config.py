"""
Configuration settings for the application.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Redis / queue settings
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    EMBEDDINGS_STREAM_KEY: str = os.getenv("EMBEDDINGS_STREAM_KEY", "embeddings:jobs")
    EMBEDDINGS_CONSUMER_GROUP: str = os.getenv(
        "EMBEDDINGS_CONSUMER_GROUP",
        "embeddings-workers",
    )
    DLQ_STREAM_KEY: str = os.getenv("DLQ_STREAM_KEY", "embeddings:dlq")
    BATCH_MAX_MESSAGES: int = int(os.getenv("BATCH_MAX_MESSAGES", "32"))
    BATCH_MAX_WAIT_MS: int = int(os.getenv("BATCH_MAX_WAIT_MS", "200"))
    WORKER_CONCURRENCY: int = int(os.getenv("WORKER_CONCURRENCY", "4"))

    # Qdrant settings
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_COLLECTION: str = os.getenv(
        "QDRANT_COLLECTION",
        "products_embeddings",
    )

    # Decoder / LLM settings
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    OPENAI_EMBEDDING_MODEL: str | None = os.getenv("OPENAI_EMBEDDING_MODEL")

    # Auth (optional, currently disabled)
    AUTH_REQUIRED: bool = os.getenv("AUTH_REQUIRED", "false").lower() == "true"
    JWT_JWKS_URL: str | None = os.getenv("JWT_JWKS_URL")
    JWT_AUDIENCE: str | None = os.getenv("JWT_AUDIENCE")
    JWT_ISSUER: str | None = os.getenv("JWT_ISSUER")

    @property
    def is_production(self) -> bool:
        """
        Check if running in production environment.
        """
        return self.ENVIRONMENT.lower() == "production"

    @property
    def decoder_enabled(self) -> bool:
        """Return True when a decoder client can be initialized."""
        return bool(self.OPENAI_API_KEY)

    @property
    def encoder_enabled(self) -> bool:
        """Return True when an encoder client can be initialized."""
        return bool(self.OPENAI_API_KEY and self.OPENAI_EMBEDDING_MODEL)

    @property
    def auth_configured(self) -> bool:
        """Indicates whether JWT verification is configured."""
        return bool(self.JWT_JWKS_URL or self.JWT_ISSUER or self.JWT_AUDIENCE)

    def __init__(self):
        self.env = os.getenv("ENV", "dev")
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        logging.basicConfig(level=self.log_level)
        self.logger = logging.getLogger(__name__)

        self.logger.debug(
            f"Config initialized with env={self.env}, debug={self.debug}, "
            f"log_level={self.log_level}"
        )


# Create a global settings instance for import
settings = Settings()
