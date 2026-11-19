import asyncio
import json
from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from orders_data_analysis.api.questions import create_app
from orders_data_analysis.database.models import Order
from orders_data_analysis.database.query_validation import (
    QueryExecutionTimeout,
    execute_read_only_query,
)
from orders_data_analysis.database.sqlite import (
    create_sqlite_engine,
    initialize_database,
)
from orders_data_analysis.llm.client import (
    LLMServiceError,
)
from orders_data_analysis.llm.factory import create_sql_generator_from_environment
from orders_data_analysis.llm.openai_compatible import (
    SCHEMA_DESCRIPTION,
    OpenAICompatibleSqlGenerator,
)


class FixedSqlGenerator:
    """Return a fixed query and record the question sent by the API."""

    def __init__(self, sql: str | Exception) -> None:
        self.sql = sql
        self.question: str | None = None

    async def generate_sql(self, question: str) -> str:
        self.question = question
        if isinstance(self.sql, Exception):
            raise self.sql
        return self.sql


def make_engine(tmp_path):
    """Create a database with accepted and non-accepted example orders."""

    engine = create_sqlite_engine(tmp_path / "api.db")
    initialize_database(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Order(
                    date=date(2026, 3, 5),
                    customer="Ada",
                    country="Spain",
                    product="Book",
                    amount=Decimal("12.50"),
                    status="accepted",
                ),
                Order(
                    date=date(2026, 3, 6),
                    customer="Ben",
                    country="Spain",
                    product="Pen",
                    amount=Decimal("30.00"),
                    status="pending",
                ),
                Order(
                    date=date(2026, 3, 7),
                    customer="Cy",
                    country="Spain",
                    product="Pencil",
                    amount=Decimal("100.00"),
                    status="rejected",
                ),
                Order(
                    date=date(2026, 3, 8),
                    customer="Dee",
                    country="France",
                    product="Book",
                    amount=Decimal("7.00"),
                    status="accepted",
                ),
            ]
        )
        session.commit()
    return engine


def post_question(app, question: str):
    """Call the ASGI app without starting an external HTTP server."""

    async def send_request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post("/questions", json={"question": question})

    return asyncio.run(send_request())


def test_question_endpoint_returns_results_from_accepted_sales_view(tmp_path):
    """Check a natural-language question is translated and safely answered."""

    engine = make_engine(tmp_path)
    generator = FixedSqlGenerator(
        "SELECT month, country, total_amount "
        "FROM sales_by_month_country "
        "WHERE month = '2026-03' AND country = 'Spain'"
    )
    app = create_app(engine=engine, sql_generator=generator)

    response = post_question(app, "How much did we sell in Spain in March?")

    assert response.status_code == 200
    assert generator.question == "How much did we sell in Spain in March?"
    assert response.json() == {
        "question": "How much did we sell in Spain in March?",
        "columns": ["month", "country", "total_amount"],
        "rows": [{"month": "2026-03", "country": "Spain", "total_amount": 12.5}],
        "truncated": False,
    }
    engine.dispose()


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "SELECT * FROM orders",
        "SELECT * FROM top_customers; DELETE FROM orders",
        "SELECT load_extension('unsafe') FROM top_customers",
    ],
)
def test_question_endpoint_rejects_unsafe_or_unapproved_sql(tmp_path, sql):
    """Check invalid SQL cannot read base tables, write, or call unsafe funcs."""

    engine = make_engine(tmp_path)
    app = create_app(engine=engine, sql_generator=FixedSqlGenerator(sql))

    response = post_question(app, "Show sales")

    assert response.status_code == 422
    assert "not allowed" in response.json()["detail"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 4
    engine.dispose()


def test_question_endpoint_returns_clear_error_when_llm_fails(tmp_path):
    """Check LLM failures return a gateway error without exposing internals."""

    engine = make_engine(tmp_path)
    app = create_app(
        engine=engine,
        sql_generator=FixedSqlGenerator(LLMServiceError("provider detail")),
    )

    response = post_question(app, "Show sales")

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The language model could not generate a query."
    }
    assert "provider detail" not in response.text
    engine.dispose()


def test_question_endpoint_reports_missing_llm_configuration(tmp_path, monkeypatch):
    """Check missing model credentials produce an actionable service error."""

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    engine = make_engine(tmp_path)
    app = create_app(engine=engine)

    response = post_question(app, "Show sales")

    assert response.status_code == 503
    assert "LLM_API_KEY" in response.json()["detail"]
    engine.dispose()


def test_question_endpoint_requires_an_explicit_provider(tmp_path, monkeypatch):
    """Check the application does not silently assume a model vendor."""

    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    engine = make_engine(tmp_path)
    app = create_app(engine=engine)

    response = post_question(app, "Show sales")

    assert response.status_code == 503
    assert "LLM_PROVIDER" in response.json()["detail"]
    engine.dispose()


def test_openai_compatible_client_sends_question_and_allowed_schema():
    """Check the provider adapter sends only the prompt and view schema."""

    observed_request = {}

    def handle_request(request: httpx.Request) -> httpx.Response:
        observed_request["url"] = str(request.url)
        observed_request["authorization"] = request.headers["Authorization"]
        observed_request["body"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "SELECT * FROM top_customers"}}]},
        )

    generator = OpenAICompatibleSqlGenerator(
        api_key="test-token",
        model="test-model",
        base_url="https://llm.example/v1/",
        transport=httpx.MockTransport(handle_request),
    )

    sql = asyncio.run(generator.generate_sql("Who are the top customers?"))

    assert sql == "SELECT * FROM top_customers"
    assert observed_request["url"] == "https://llm.example/v1/chat/completions"
    assert observed_request["authorization"] == "Bearer test-token"
    assert "Who are the top customers?" in observed_request["body"]
    body = json.loads(observed_request["body"])
    assert SCHEMA_DESCRIPTION in body["messages"][0]["content"]
    assert body["messages"][1]["content"] == "Who are the top customers?"


def test_factory_selects_openai_compatible_only_when_requested(monkeypatch):
    """Check provider adapters are selected explicitly from configuration."""

    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_API_KEY", "test-token")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    generator = create_sql_generator_from_environment()

    assert isinstance(generator, OpenAICompatibleSqlGenerator)


def test_query_result_is_truncated_at_requested_row_limit(tmp_path):
    """Check query execution returns no more than the configured row limit."""

    engine = make_engine(tmp_path)

    result = execute_read_only_query(
        engine,
        "SELECT customer, total_amount FROM top_customers",
        max_rows=1,
    )

    assert len(result.rows) == 1
    assert result.truncated is True
    engine.dispose()


def test_query_execution_stops_after_time_limit(tmp_path):
    """Check SQLite interrupts a permitted query that runs beyond its budget."""

    engine = make_engine(tmp_path)
    with Session(engine) as session:
        session.add_all(
            [
                Order(
                    date=date(2026, 3, index),
                    customer=f"Extra customer {index}",
                    country="Spain",
                    product=f"Product {index}",
                    amount=Decimal("1.00"),
                    status="accepted",
                )
                for index in range(1, 9)
            ]
        )
        session.commit()
    aliases = " ".join(
        f"CROSS JOIN top_customers AS customer_{index}" for index in range(2, 10)
    )
    sql = (
        f"SELECT SUM(customer_1.total_amount) FROM top_customers "
        f"AS customer_1 {aliases}"
    )

    with pytest.raises(QueryExecutionTimeout):
        execute_read_only_query(engine, sql, timeout_seconds=0.01)

    engine.dispose()
