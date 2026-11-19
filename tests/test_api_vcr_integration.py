"""Offline-replayable HTTP integration coverage for the LLM-backed API."""

from __future__ import annotations

import asyncio
import gzip
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
import vcr
from sqlalchemy.orm import Session
from vcr.filters import decode_response

from orders_data_analysis.api.questions import create_app
from orders_data_analysis.database.models import Order
from orders_data_analysis.database.sqlite import (
    create_sqlite_engine,
    initialize_database,
)

CASSETTE_DIRECTORY = Path(__file__).parent / "cassettes"
QUESTION = "How much accepted sales were recorded in Spain in March 2026?"


def _redact_request(request: Any) -> Any:
    """Keep request metadata but omit the prompt body from the cassette."""

    request.body = b""
    return request


def _redact_response(response: dict[str, Any]) -> dict[str, Any] | None:
    """Keep only generated SQL and content type; drop provider metadata."""

    response = decode_response(response)
    try:
        raw_body = response["body"]["string"]
        body_text = (
            raw_body.decode("utf-8") if isinstance(raw_body, bytes) else raw_body
        )
        content = json.loads(body_text)["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(content, str):
        return None

    response["body"]["string"] = json.dumps(
        {"choices": [{"message": {"content": content}}]}
    ).encode("utf-8")
    response["headers"] = {"content-type": ["application/json"]}
    return response


def _send_question(app):
    """Post the fixed synthetic question through the ASGI app."""

    async def send_request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost"
        ) as client:
            return await client.post("/questions", json={"question": QUESTION})

    return asyncio.run(send_request())


def _build_recorder(record_mode: str) -> vcr.VCR:
    """Configure replay/recording with request and response redaction."""

    return vcr.VCR(
        cassette_library_dir=str(CASSETTE_DIRECTORY),
        record_mode=record_mode,
        filter_headers=[
            "authorization",
            "api-key",
            "x-api-key",
            "set-cookie",
            "content-length",
        ],
        before_record_request=_redact_request,
        before_record_response=_redact_response,
        record_on_exception=False,
        ignore_localhost=True,
    )


def test_vcr_recording_scrubs_request_credentials_and_body():
    """Check VCR removes auth headers and request bodies before recording."""

    recorder = _build_recorder("none")
    scrub_request = recorder._build_before_record_request({})
    request = vcr.request.Request(
        method="POST",
        uri="https://api.openai.com/v1/chat/completions",
        body=b'{"question":"private customer data"}',
        headers={
            "authorization": "Bearer test-secret",
            "x-api-key": "test-api-key",
            "content-length": "42",
            "content-type": "application/json",
        },
    )

    redacted_request = scrub_request(request)

    assert redacted_request.body == b""
    assert "authorization" not in redacted_request.headers
    assert "x-api-key" not in redacted_request.headers
    assert "content-length" not in redacted_request.headers


def test_vcr_recording_keeps_only_model_sql_in_response():
    """Check compressed provider replies are decoded and sanitized for cassettes."""

    response = {
        "body": {
            "string": gzip.compress(
                json.dumps(
                    {
                        "id": "request-private-id",
                        "choices": [
                            {
                                "message": {
                                    "content": "SELECT * FROM top_customers",
                                }
                            }
                        ],
                    }
                ).encode("utf-8")
            )
        },
        "headers": {
            "content-type": ["application/json"],
            "content-encoding": ["gzip"],
            "set-cookie": ["secret-cookie"],
            "x-request-id": ["request-private-id"],
        },
    }

    redacted_response = _redact_response(response)

    assert redacted_response is not None
    assert redacted_response["headers"] == {"content-type": ["application/json"]}
    assert "request-private-id" not in str(redacted_response)
    assert "secret-cookie" not in str(redacted_response)


@pytest.mark.integration
def test_question_api_records_or_replays_real_llm_interaction(tmp_path, monkeypatch):
    """Check the full API using a real, sanitized provider interaction cassette."""

    record_mode = os.getenv("ORDERS_VCR_RECORD_MODE", "none").casefold()
    cassette = CASSETTE_DIRECTORY / "accepted_sales_question.yaml"
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if record_mode != "none":
        if not api_key or not os.getenv("LLM_MODEL"):
            pytest.skip(
                "Recording requires LLM_API_KEY (or OPENAI_API_KEY) and LLM_MODEL."
            )
        monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    else:
        if not cassette.exists():
            pytest.skip(
                "No real-provider cassette yet; set ORDERS_VCR_RECORD_MODE=once "
                "with LLM_API_KEY and LLM_MODEL to create it."
            )
        api_key = "vcr-playback-placeholder"
        monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
        monkeypatch.setenv("LLM_API_KEY", api_key)
        monkeypatch.setenv("LLM_MODEL", "vcr-test-model")
        monkeypatch.delenv("LLM_BASE_URL", raising=False)
    assert api_key is not None

    engine = create_sqlite_engine(tmp_path / "vcr-api.db")
    initialize_database(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Order(
                    date=date(2026, 3, 5),
                    customer="Ada Example",
                    country="Spain",
                    product="Notebook",
                    amount=Decimal("12.50"),
                    status="accepted",
                ),
                Order(
                    date=date(2026, 3, 6),
                    customer="Grace Example",
                    country="France",
                    product="Notebook",
                    amount=Decimal("40.00"),
                    status="accepted",
                ),
                Order(
                    date=date(2026, 2, 5),
                    customer="Lin Example",
                    country="Spain",
                    product="Notebook",
                    amount=Decimal("25.00"),
                    status="accepted",
                ),
            ]
        )
        session.commit()

    app = create_app(engine=engine)
    with _build_recorder(record_mode).use_cassette(cassette.name):
        response = _send_question(app)

    assert response.status_code == 200
    result = response.json()
    assert len(result["rows"]) == 1
    row = result["rows"][0]
    if {"month", "country", "total_amount"}.issubset(row):
        assert row == {
            "month": "2026-03",
            "country": "Spain",
            "total_amount": 12.5,
        }
    else:
        assert len(row) == 1
        assert next(iter(row.values())) == 12.5
    assert result["truncated"] is False

    cassette_text = cassette.read_text(encoding="utf-8")
    assert api_key not in cassette_text
    assert "vcr-playback-placeholder" not in cassette_text
    assert "Authorization: Bearer" not in cassette_text
    assert "content-length" not in cassette_text
    engine.dispose()
