"""Provider-neutral contract for natural-language to SQL clients."""

from typing import Protocol


class LLMConfigurationError(RuntimeError):
    """Raised when required model provider settings are missing or unsupported."""


class LLMServiceError(RuntimeError):
    """Raised when a configured model service fails or returns invalid data."""


class SqlGenerator(Protocol):
    """Interface for provider implementations that return candidate SQL."""

    async def generate_sql(self, question: str) -> str:
        """Return one candidate SQL query for a natural-language question."""
