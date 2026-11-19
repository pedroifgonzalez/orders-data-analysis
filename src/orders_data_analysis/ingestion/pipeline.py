"""Read order CSV files in bounded batches and persist valid unique orders."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Engine, insert, select, text

from orders_data_analysis.data_contracts import CSV_COLUMNS
from orders_data_analysis.database.models import Order
from orders_data_analysis.database.sqlite import initialize_database
from orders_data_analysis.ingestion.validation import validate_order_row

DEFAULT_CHUNK_SIZE = 10_000
_BATCH_COLUMNS = (
    "source_index",
    "order_date",
    "customer",
    "country",
    "product",
    "amount_text",
    "status",
    "customer_key",
    "product_key",
    "exact_fingerprint",
)


class CsvIngestionError(ValueError):
    """Raised when a CSV cannot be read according to the expected file schema."""


@dataclass(frozen=True)
class IngestionReport:
    """Summary of the rows read, rejected, deduplicated, and inserted."""

    source_path: Path
    rows_read: int
    rows_valid: int
    rows_rejected: int
    exact_duplicates: int
    business_duplicates: int
    rows_inserted: int
    rejected_by_reason: dict[str, int]


def _read_header(source_path: Path) -> list[str]:
    try:
        header = pd.read_csv(
            source_path,
            nrows=0,
            dtype="string",
            keep_default_na=False,
            na_filter=False,
            skip_blank_lines=False,
            on_bad_lines="error",
        )
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as error:
        raise CsvIngestionError(f"Cannot read CSV header: {error}") from error

    columns = list(header.columns)
    if len(columns) != len(CSV_COLUMNS) or set(columns) != set(CSV_COLUMNS):
        expected = ", ".join(CSV_COLUMNS)
        found = ", ".join(columns)
        raise CsvIngestionError(
            f"CSV columns must be exactly [{expected}]; found [{found}]"
        )
    return columns


def _exact_fingerprint(values: tuple[str, ...]) -> str:
    serialized = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _stage_order(order: dict[str, Any], source_index: int) -> dict[str, Any]:
    """Add ingestion-only keys and serialization to a validated order."""

    order_date = order["date"].isoformat()
    amount_text = f"{order['amount']:.2f}"
    exact_values = (
        order_date,
        order["customer"],
        order["country"],
        order["product"],
        amount_text,
        order["status"],
    )
    return {
        "source_index": source_index,
        "order_date": order_date,
        "customer": order["customer"],
        "country": order["country"],
        "product": order["product"],
        "amount_text": amount_text,
        "status": order["status"],
        "customer_key": order["customer"].casefold(),
        "product_key": order["product"].casefold(),
        "exact_fingerprint": _exact_fingerprint(exact_values),
    }


def _create_temporary_tables(connection: Any) -> None:
    _drop_temporary_tables(connection)
    connection.exec_driver_sql("""
        CREATE TEMP TABLE _seen_order_keys (
            customer_key TEXT NOT NULL,
            order_date TEXT NOT NULL,
            product_key TEXT NOT NULL,
            first_source_index INTEGER NOT NULL,
            exact_fingerprint TEXT NOT NULL,
            PRIMARY KEY (customer_key, order_date, product_key)
        ) WITHOUT ROWID
        """)
    connection.exec_driver_sql("""
        CREATE TEMP TABLE _batch_order_rows (
            source_index INTEGER PRIMARY KEY,
            order_date TEXT NOT NULL,
            customer TEXT NOT NULL,
            country TEXT NOT NULL,
            product TEXT NOT NULL,
            amount_text TEXT NOT NULL,
            status TEXT NOT NULL,
            customer_key TEXT NOT NULL,
            product_key TEXT NOT NULL,
            exact_fingerprint TEXT NOT NULL
        )
        """)


def _drop_temporary_tables(connection: Any) -> None:
    connection.exec_driver_sql("DROP TABLE IF EXISTS _batch_order_rows")
    connection.exec_driver_sql("DROP TABLE IF EXISTS _seen_order_keys")


def _stage_batch(connection: Any, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    parameters = ", ".join(f":{column}" for column in _BATCH_COLUMNS)
    columns = ", ".join(_BATCH_COLUMNS)
    connection.execute(
        text(f"INSERT INTO _batch_order_rows ({columns}) VALUES ({parameters})"),
        rows,
    )
    connection.execute(text("""
            INSERT OR IGNORE INTO _seen_order_keys (
                customer_key, order_date, product_key,
                first_source_index, exact_fingerprint
            )
            SELECT customer_key, order_date, product_key,
                   source_index, exact_fingerprint
            FROM _batch_order_rows
            ORDER BY source_index
            """))


def _seed_existing_order_keys(connection: Any, chunk_size: int) -> None:
    """Load prior database keys in batches so repeat imports remain idempotent."""

    result = connection.execute(
        select(
            Order.id,
            Order.date,
            Order.customer,
            Order.country,
            Order.product,
            Order.amount,
            Order.status,
        ).order_by(Order.id)
    )
    mapped_result = result.mappings()
    while existing_rows := mapped_result.fetchmany(chunk_size):
        keys: list[dict[str, Any]] = []
        for row in existing_rows:
            order_date = row["date"].isoformat()
            customer = row["customer"].strip()
            country = row["country"].strip()
            product = row["product"].strip()
            amount_text = f"{Decimal(str(row['amount'])):.2f}"
            status = row["status"].strip().casefold()
            exact_values = (
                order_date,
                customer,
                country,
                product,
                amount_text,
                status,
            )
            keys.append(
                {
                    "customer_key": customer.casefold(),
                    "order_date": order_date,
                    "product_key": product.casefold(),
                    "first_source_index": -int(row["id"]),
                    "exact_fingerprint": _exact_fingerprint(exact_values),
                }
            )
        connection.execute(
            text("""
                INSERT OR IGNORE INTO _seen_order_keys (
                    customer_key, order_date, product_key,
                    first_source_index, exact_fingerprint
                )
                VALUES (
                    :customer_key, :order_date, :product_key,
                    :first_source_index, :exact_fingerprint
                )
                """),
            keys,
        )


def _insert_first_occurrences(connection: Any) -> tuple[int, int, int]:
    duplicate_counts = connection.execute(text("""
            SELECT
                COALESCE(SUM(CASE
                    WHEN b.exact_fingerprint = s.exact_fingerprint THEN 1 ELSE 0
                END), 0) AS exact_duplicates,
                COALESCE(SUM(CASE
                    WHEN b.exact_fingerprint != s.exact_fingerprint THEN 1 ELSE 0
                END), 0) AS business_duplicates
            FROM _batch_order_rows AS b
            JOIN _seen_order_keys AS s
              ON s.customer_key = b.customer_key
             AND s.order_date = b.order_date
             AND s.product_key = b.product_key
            WHERE s.first_source_index != b.source_index
            """)).mappings().one()

    first_occurrences = connection.execute(text("""
            SELECT b.order_date, b.customer, b.country, b.product,
                   b.amount_text, b.status
            FROM _batch_order_rows AS b
            JOIN _seen_order_keys AS s
              ON s.customer_key = b.customer_key
             AND s.order_date = b.order_date
             AND s.product_key = b.product_key
             AND s.first_source_index = b.source_index
            ORDER BY b.source_index
            """)).mappings()
    orders = [
        {
            "date": date.fromisoformat(row["order_date"]),
            "customer": row["customer"],
            "country": row["country"],
            "product": row["product"],
            "amount": Decimal(row["amount_text"]),
            "status": row["status"],
        }
        for row in first_occurrences
    ]
    if orders:
        connection.execute(insert(Order), orders)

    connection.execute(text("DELETE FROM _batch_order_rows"))
    return (
        len(orders),
        int(duplicate_counts["exact_duplicates"]),
        int(duplicate_counts["business_duplicates"]),
    )


def ingest_orders_csv(
    source_path: str | Path,
    engine: Engine,
    *,
    reference_date: date | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> IngestionReport:
    """Validate, deduplicate, and batch-insert orders from a CSV file.

    The full import uses one database transaction. Only a bounded Pandas chunk,
    validation results, and SQLite temporary duplicate keys are held at a time.
    """

    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")

    path = Path(source_path)
    columns = _read_header(path)
    as_of = reference_date or datetime.now(timezone.utc).date()
    initialize_database(engine)

    rows_read = 0
    rows_valid = 0
    rows_rejected = 0
    exact_duplicates = 0
    business_duplicates = 0
    rows_inserted = 0
    rejection_counts: Counter[str] = Counter()

    reader = pd.read_csv(
        path,
        chunksize=chunk_size,
        dtype={column: "string" for column in columns},
        keep_default_na=False,
        na_filter=False,
        skip_blank_lines=False,
        on_bad_lines="error",
    )

    try:
        with engine.begin() as connection:
            _create_temporary_tables(connection)
            try:
                _seed_existing_order_keys(connection, chunk_size)
                for chunk in reader:
                    chunk = chunk.loc[:, CSV_COLUMNS]
                    valid_rows: list[dict[str, Any]] = []
                    for offset, values in enumerate(
                        chunk.itertuples(index=False, name=None)
                    ):
                        source_index = rows_read + offset + 1
                        order, errors = validate_order_row(values, as_of)
                        if errors:
                            rows_rejected += 1
                            rejection_counts.update(errors)
                        else:
                            assert order is not None
                            valid_rows.append(_stage_order(order, source_index))

                    rows_read += len(chunk)
                    rows_valid += len(valid_rows)
                    connection.execute(text("DELETE FROM _batch_order_rows"))
                    _stage_batch(connection, valid_rows)
                    inserted, exact, business = _insert_first_occurrences(connection)
                    rows_inserted += inserted
                    exact_duplicates += exact
                    business_duplicates += business
            finally:
                _drop_temporary_tables(connection)
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as error:
        raise CsvIngestionError(f"Cannot parse CSV data: {error}") from error

    return IngestionReport(
        source_path=path,
        rows_read=rows_read,
        rows_valid=rows_valid,
        rows_rejected=rows_rejected,
        exact_duplicates=exact_duplicates,
        business_duplicates=business_duplicates,
        rows_inserted=rows_inserted,
        rejected_by_reason=dict(rejection_counts),
    )
