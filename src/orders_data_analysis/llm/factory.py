"""Select a concrete LLM adapter from explicit deployment configuration."""

from __future__ import annotations

import os

from orders_data_analysis.llm.client import LLMConfigurationError, SqlGenerator
from orders_data_analysis.llm.openai_compatible import OpenAICompatibleSqlGenerator


def create_sql_generator_from_environment() -> SqlGenerator:
    """Create the configured provider adapter; never assume a provider."""

    provider = os.getenv("LLM_PROVIDER", "").strip().casefold()
    if not provider:
        raise LLMConfigurationError("Set LLM_PROVIDER to the provider adapter to use.")
    if provider == "openai-compatible":
        return OpenAICompatibleSqlGenerator.from_environment()
    raise LLMConfigurationError(
        f"LLM_PROVIDER {provider!r} has no adapter configured in this project."
    )
