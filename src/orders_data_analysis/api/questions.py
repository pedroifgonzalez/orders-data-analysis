"""Expose the question endpoint and orchestrate LLM query generation safely."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Engine
from starlette.concurrency import run_in_threadpool

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
    """Tabular query results returned to the API caller."""

    question: str
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool


def create_app(
    *, engine: Engine | None = None, sql_generator: SqlGenerator | None = None
) -> FastAPI:
    """Create an application with injectable database and model dependencies."""

    owns_engine = engine is None
    database_engine = (
        engine
        if engine is not None
        else create_sqlite_engine(os.getenv("ORDERS_DATABASE_PATH", "data/orders.db"))
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        initialize_database(database_engine)
        try:
            yield
        finally:
            if owns_engine:
                database_engine.dispose()

    app = FastAPI(title="Orders Data Analysis API", lifespan=lifespan)
    app.state.engine = database_engine
    app.state.sql_generator = sql_generator

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Return a lightweight process health response."""

        return {"status": "ok"}

    @app.post("/questions", response_model=QuestionResponse)
    async def answer_question(request: QuestionRequest) -> QuestionResponse:
        """Generate, validate, and execute a read-only analytical query."""

        generator = app.state.sql_generator
        if generator is None:
            try:
                generator = create_sql_generator_from_environment()
            except LLMConfigurationError as error:
                raise HTTPException(status_code=503, detail=str(error)) from error

        try:
            sql = await generator.generate_sql(request.question)
        except LLMServiceError as error:
            raise HTTPException(
                status_code=502,
                detail="The language model could not generate a query.",
            ) from error

        try:
            result = await run_in_threadpool(
                execute_read_only_query, app.state.engine, sql
            )
        except QueryValidationError as error:
            raise HTTPException(
                status_code=422,
                detail="The language model returned a query that is not allowed.",
            ) from error
        except QueryExecutionTimeout as error:
            raise HTTPException(
                status_code=504,
                detail="The query exceeded the database time limit.",
            ) from error
        except QueryExecutionError as error:
            raise HTTPException(
                status_code=422,
                detail="The query could not run against the approved views.",
            ) from error

        return QuestionResponse(
            question=request.question,
            columns=result.columns,
            rows=result.rows,
            truncated=result.truncated,
        )

    return app
