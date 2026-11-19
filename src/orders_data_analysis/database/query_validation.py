"""Validate and safely execute read-only SQLite queries from the LLM."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine

ALLOWED_VIEWS = frozenset({"sales_by_month_country", "top_customers"})
ALLOWED_FUNCTIONS = frozenset(
    {
        "abs",
        "avg",
        "coalesce",
        "count",
        "date",
        "ifnull",
        "length",
        "lower",
        "max",
        "min",
        "round",
        "strftime",
        "substr",
        "sum",
        "upper",
    }
)
MAX_SQL_LENGTH = 10_000
DEFAULT_MAX_ROWS = 100
DEFAULT_QUERY_TIMEOUT_SECONDS = 2.0


class QueryValidationError(ValueError):
    """Raised when SQL is not a single read-only query on approved views."""


class QueryExecutionTimeout(TimeoutError):
    """Raised when a read query exceeds its execution time budget."""


class QueryExecutionError(RuntimeError):
    """Raised when an approved query cannot be executed against the views."""


@dataclass(frozen=True)
class QueryResult:
    """Bounded rows and column names returned by an analytical query."""

    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool


def _make_authorizer(view_reads: set[str]):
    """Allow SELECTs that read only approved views and their base table."""

    def authorize(
        action: int,
        first_argument: str | None,
        second_argument: str | None,
        database_name: str | None,
        source: str | None,
    ) -> int:
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK

        if action == sqlite3.SQLITE_READ:
            table_name = (first_argument or "").casefold()
            source_name = (source or "").casefold()
            if (
                table_name in ALLOWED_VIEWS
                and not source_name
                and database_name
                in {
                    None,
                    "main",
                }
            ):
                view_reads.add(table_name)
                return sqlite3.SQLITE_OK
            if (
                database_name == "main"
                and table_name == "orders"
                and source_name in ALLOWED_VIEWS
            ):
                view_reads.add(source_name)
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        if action == sqlite3.SQLITE_FUNCTION:
            function_name = (second_argument or first_argument or "").casefold()
            return (
                sqlite3.SQLITE_OK
                if function_name in ALLOWED_FUNCTIONS
                else sqlite3.SQLITE_DENY
            )

        return sqlite3.SQLITE_DENY

    return authorize


def _validate_with_sqlite(
    raw_connection: sqlite3.Connection, sql: str, view_reads: set[str]
) -> None:
    if not sql or len(sql) > MAX_SQL_LENGTH:
        raise QueryValidationError("The query is empty or exceeds the SQL size limit.")

    try:
        raw_connection.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
    except sqlite3.DatabaseError as error:
        if getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT:
            raise QueryExecutionTimeout(
                "The query exceeded the execution time limit."
            ) from error
        raise QueryValidationError(
            "Only one read-only SELECT from the approved analytical views is allowed."
        ) from error

    if not view_reads:
        raise QueryValidationError(
            "The query must read from an approved analytical view."
        )


def execute_read_only_query(
    engine: Engine,
    sql: str,
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
    timeout_seconds: float = DEFAULT_QUERY_TIMEOUT_SECONDS,
) -> QueryResult:
    """Validate and execute SQL under SQLite read, row, and time limits."""

    if max_rows < 1:
        raise ValueError("max_rows must be at least 1")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    deadline = time.monotonic() + timeout_seconds
    view_reads: set[str] = set()
    with engine.connect() as connection:
        raw_connection = connection.connection.driver_connection
        if not isinstance(raw_connection, sqlite3.Connection):
            raise RuntimeError("Read-only query execution requires SQLite.")
        raw_connection.execute("PRAGMA query_only = ON")
        raw_connection.set_authorizer(_make_authorizer(view_reads))
        raw_connection.set_progress_handler(
            lambda: int(time.monotonic() > deadline), 1_000
        )
        cursor: sqlite3.Cursor | None = None
        try:
            _validate_with_sqlite(raw_connection, sql, view_reads)
            cursor = raw_connection.execute(sql)
            if cursor.description is None:
                raise QueryValidationError("The query did not return tabular results.")
            columns = [description[0] for description in cursor.description]
            fetched = cursor.fetchmany(max_rows + 1)
            truncated = len(fetched) > max_rows
            rows = [
                {column: value for column, value in zip(columns, row, strict=True)}
                for row in fetched[:max_rows]
            ]
            return QueryResult(columns=columns, rows=rows, truncated=truncated)
        except sqlite3.DatabaseError as error:
            if getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT:
                raise QueryExecutionTimeout(
                    "The query exceeded the execution time limit."
                ) from error
            if isinstance(error, sqlite3.DatabaseError) and view_reads:
                raise QueryExecutionError(
                    "The query could not be executed against the approved views."
                ) from error
            raise QueryValidationError(
                "Only one read-only SELECT from the approved analytical views is allowed."
            ) from error
        finally:
            if cursor is not None:
                cursor.close()
            raw_connection.set_authorizer(None)
            raw_connection.set_progress_handler(None, 0)
            raw_connection.execute("PRAGMA query_only = OFF")
