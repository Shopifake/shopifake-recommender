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

    @property
    def is_production(self) -> bool:
        """
        Check if running in production environment.
        """
        return self.ENVIRONMENT.lower() == "production"


settings = Settings()
