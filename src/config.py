"""
Configuration settings for the application.
"""

import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """
    Application settings loaded from environment variables.
    """

    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    # Qdrant settings
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://qdrant:6333")

    # Decoder / LLM settings
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL")

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


settings = Settings()
