"""Environment-backed settings shared by the API and command-line tools."""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path


def _positive_integer(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    try:
        value = default if raw_value is None else int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer.") from error
    if value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _positive_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    try:
        value = default if raw_value is None else float(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive number.") from error
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive number.")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated runtime configuration loaded from environment variables."""

    database_path: Path
    csv_path: Path
    llm_provider: str | None
    llm_api_key: str | None = field(repr=False, compare=False)
    llm_model: str | None
    llm_base_url: str
    llm_timeout_seconds: float
    query_timeout_seconds: float
    query_max_rows: int
    ingestion_chunk_size: int
    log_level: str

    @classmethod
    def from_environment(cls) -> Settings:
        """Read supported settings without exposing secret values in errors."""

        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError(
                "LOG_LEVEL must be CRITICAL, ERROR, WARNING, INFO, or DEBUG."
            )

        provider = os.getenv("LLM_PROVIDER", "").strip().casefold() or None
        api_key = (
            os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        ).strip()
        model = os.getenv("LLM_MODEL", "").strip() or None

        return cls(
            database_path=Path(os.getenv("ORDERS_DATABASE_PATH", "data/orders.db")),
            csv_path=Path(os.getenv("ORDERS_CSV_PATH", "data/orders.csv")),
            llm_provider=provider,
            llm_api_key=api_key or None,
            llm_model=model,
            llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip(
                "/"
            ),
            llm_timeout_seconds=_positive_float("LLM_TIMEOUT_SECONDS", 30.0),
            query_timeout_seconds=_positive_float("QUERY_TIMEOUT_SECONDS", 2.0),
            query_max_rows=_positive_integer("QUERY_MAX_ROWS", 100),
            ingestion_chunk_size=_positive_integer(
                "ORDERS_INGESTION_CHUNK_SIZE", 10_000
            ),
            log_level=log_level,
        )


def configure_logging(settings: Settings) -> None:
    """Set concise logging defaults while preserving host handlers if present."""

    logging.basicConfig(
        level=settings.log_level,
        format="%(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("orders_data_analysis").setLevel(settings.log_level)
