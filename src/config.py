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

    # Database settings
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite+aiosqlite:///./app.db"  # Default: SQLite for dev/test
    )

    # PostgreSQL settings (for production)
    POSTGRES_USER: str | None = os.getenv("POSTGRES_USER")
    POSTGRES_PASSWORD: str | None = os.getenv("POSTGRES_PASSWORD")
    POSTGRES_HOST: str | None = os.getenv("POSTGRES_HOST")
    POSTGRES_PORT: str | None = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str | None = os.getenv("POSTGRES_DB")

    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    @property
    def is_production(self) -> bool:
        """
        Check if running in production environment.
        """
        return self.ENVIRONMENT.lower() == "production"

    @property
    def database_url(self) -> str:
        """
        Get the appropriate database URL based on environment.

        In production, constructs PostgreSQL URL from individual vars.
        In dev/test, uses SQLite.
        """
        if self.is_production and self.POSTGRES_USER:
            # Production: use PostgreSQL
            return (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        # Development/Test: use SQLite
        return self.DATABASE_URL


settings = Settings()
