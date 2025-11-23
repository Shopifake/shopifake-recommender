"""Base worker functionality for async job processing."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseWorker(ABC):
    """Abstract base class for async workers."""

    def __init__(self, consumer_name: str | None = None):
        self.consumer_name = consumer_name or self._build_consumer_name()
        self._shutdown_event = asyncio.Event()

    @abstractmethod
    async def run_forever(self) -> None:
        """Main worker loop. Should be implemented by subclasses."""
        pass

    @abstractmethod
    def _build_consumer_name(self) -> str:
        """Build a unique consumer name for this worker instance."""
        pass

    def shutdown(self) -> None:
        """Signal the worker to shut down gracefully."""
        self._shutdown_event.set()

    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_event.is_set()
