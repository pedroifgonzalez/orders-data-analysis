"""Select a concrete LLM adapter from explicit deployment configuration."""

from __future__ import annotations

from orders_data_analysis.llm.client import LLMConfigurationError, SqlGenerator
from orders_data_analysis.llm.openai_compatible import OpenAICompatibleSqlGenerator
from orders_data_analysis.settings import Settings


def create_sql_generator_from_environment(
    settings: Settings | None = None,
) -> SqlGenerator:
    """Create the configured provider adapter; never assume a provider."""

    if settings is None:
        try:
            settings = Settings.from_environment()
        except ValueError as error:
            raise LLMConfigurationError(str(error)) from error
    provider = settings.llm_provider
    if not provider:
        raise LLMConfigurationError("Set LLM_PROVIDER to the provider adapter to use.")
    if provider == "openai-compatible":
        if not settings.llm_api_key:
            raise LLMConfigurationError("Set LLM_API_KEY or OPENAI_API_KEY.")
        if not settings.llm_model:
            raise LLMConfigurationError("Set LLM_MODEL to the model identifier.")
        return OpenAICompatibleSqlGenerator(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    raise LLMConfigurationError(
        f"LLM_PROVIDER {provider!r} has no adapter configured in this project."
    )
