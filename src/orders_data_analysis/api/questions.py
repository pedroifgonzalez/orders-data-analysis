"""Expose the question endpoint and orchestrate LLM query generation safely."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine, func, select
from starlette.concurrency import run_in_threadpool

from orders_data_analysis.database.models import Order
from orders_data_analysis.database.query_validation import (
    QueryExecutionError,
    QueryExecutionTimeout,
    QueryValidationError,
    execute_read_only_query,
)
from orders_data_analysis.database.sqlite import (
    create_sqlite_engine,
    initialize_database,
)
from orders_data_analysis.llm.client import (
    LLMConfigurationError,
    LLMServiceError,
    SqlGenerator,
)
from orders_data_analysis.llm.factory import create_sql_generator_from_environment
from orders_data_analysis.settings import Settings, configure_logging

logger = logging.getLogger(__name__)


class QuestionRequest(BaseModel):
    """Validated JSON request containing one natural-language question."""

    question: str = Field(min_length=1, max_length=1_000)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        """Trim whitespace and reject questions that contain no text."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("question must not be blank")
        return normalized


class QuestionResponse(BaseModel):
    """User-facing summary and tabular query results."""

    question: str
    message: str
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool


def _empty_result_message(engine: Engine) -> tuple[str, str]:
    """Explain an empty result using row counts, without logging query content."""

    with engine.connect() as connection:
        order_count = connection.scalar(select(func.count()).select_from(Order)) or 0
        accepted_count = (
            connection.scalar(
                select(func.count())
                .select_from(Order)
                .where(Order.status == "accepted")
            )
            or 0
        )

    if order_count == 0:
        return (
            "No orders are loaded in the database yet. Load the CSV with "
            "`uv run ingest-orders` and try again.",
            "database_empty",
        )
    if accepted_count == 0:
        return (
            "The database contains orders, but none are accepted. Sales reports "
            "include accepted orders only.",
            "no_accepted_orders",
        )
    return (
        "No accepted sales matched this question. Check the requested filters, "
        "such as country and month.",
        "no_matching_sales",
    )


def create_app(
    *, engine: Engine | None = None, sql_generator: SqlGenerator | None = None
) -> FastAPI:
    """Create an application with injectable database and model dependencies."""

    settings = Settings.from_environment()
    configure_logging(settings)
    owns_engine = engine is None
    database_engine = (
        engine if engine is not None else create_sqlite_engine(settings.database_path)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        initialize_database(database_engine)
        logger.info("Database schema initialized")
        try:
            yield
        finally:
            if owns_engine:
                database_engine.dispose()

    app = FastAPI(title="Orders Data Analysis API", lifespan=lifespan)
    app.state.engine = database_engine
    app.state.sql_generator = sql_generator
    app.state.settings = settings

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Return a lightweight process health response."""

        return {"status": "ok"}

    @app.post("/questions", response_model=QuestionResponse)
    async def answer_question(request: QuestionRequest) -> QuestionResponse:
        """Generate, validate, and execute a read-only analytical query."""

        started_at = time.perf_counter()
        logger.info("Question request started")
        generator = app.state.sql_generator
        if generator is None:
            try:
                generator = create_sql_generator_from_environment(settings)
            except LLMConfigurationError as error:
                logger.warning(
                    "Question request rejected: LLM configuration unavailable"
                )
                raise HTTPException(status_code=503, detail=str(error)) from error

        try:
            sql = await generator.generate_sql(request.question)
        except LLMServiceError as error:
            logger.warning("Question request failed during LLM query generation")
            raise HTTPException(
                status_code=502,
                detail="The language model could not generate a query.",
            ) from error

        try:
            result = await run_in_threadpool(
                execute_read_only_query,
                app.state.engine,
                sql,
                max_rows=settings.query_max_rows,
                timeout_seconds=settings.query_timeout_seconds,
            )
        except QueryValidationError as error:
            logger.warning("Question request rejected: generated query not allowed")
            raise HTTPException(
                status_code=422,
                detail="The language model returned a query that is not allowed.",
            ) from error
        except QueryExecutionTimeout as error:
            logger.warning("Question request timed out during database query")
            raise HTTPException(
                status_code=504,
                detail="The query exceeded the database time limit.",
            ) from error
        except QueryExecutionError as error:
            logger.warning("Question request failed during database query")
            raise HTTPException(
                status_code=422,
                detail="The query could not run against the approved views.",
            ) from error

        has_values = any(
            value is not None for row in result.rows for value in row.values()
        )
        response_rows = result.rows if has_values else []
        if response_rows:
            row_count = len(response_rows)
            row_label = "row" if row_count == 1 else "rows"
            message = f"Found {row_count} matching {row_label}."
            logger.info(
                "Question request completed: rows=%d truncated=%s elapsed_ms=%d",
                len(result.rows),
                result.truncated,
                round((time.perf_counter() - started_at) * 1000),
            )
        else:
            message, empty_reason = _empty_result_message(app.state.engine)
            logger.info(
                "Question request completed with no rows: reason=%s elapsed_ms=%d",
                empty_reason,
                round((time.perf_counter() - started_at) * 1000),
            )

        return QuestionResponse(
            question=request.question,
            message=message,
            columns=result.columns,
            rows=response_rows,
            truncated=result.truncated,
        )

    return app
