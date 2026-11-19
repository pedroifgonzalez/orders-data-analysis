import csv
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from orders_data_analysis.data_contracts import CSV_COLUMNS
from orders_data_analysis.database.models import Order
from orders_data_analysis.database.sqlite import (
    create_sqlite_engine,
    initialize_database,
)
from orders_data_analysis.generator.csv_generator import generate_orders_csv
from orders_data_analysis.ingestion.pipeline import CsvIngestionError, ingest_orders_csv


def write_orders_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def test_ingestion_validates_then_deduplicates_generated_csv_across_chunks(tmp_path):
    """Check chunked ingestion stores only valid, first-occurrence orders."""

    reference_date = date(2026, 11, 18)
    source = tmp_path / "orders.csv"
    generate_orders_csv(source, reference_date=reference_date)
    engine = create_sqlite_engine(tmp_path / "orders.db")

    report = ingest_orders_csv(
        source, engine, reference_date=reference_date, chunk_size=31
    )

    assert report.rows_read == 1_000
    assert report.rows_valid == 920
    assert report.rows_rejected == 80
    assert report.exact_duplicates == 10
    assert report.business_duplicates == 10
    assert report.rows_inserted == 900
    assert sum(report.rejected_by_reason.values()) == report.rows_rejected
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 900

    repeated_report = ingest_orders_csv(
        source, engine, reference_date=reference_date, chunk_size=31
    )
    assert repeated_report.rows_inserted == 0
    assert repeated_report.exact_duplicates == 910
    assert repeated_report.business_duplicates == 10
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 900
    engine.dispose()


def test_invalid_row_cannot_suppress_valid_order_and_duplicates_cross_chunks(tmp_path):
    """Check validation runs first and duplicate keys persist between chunks."""

    source = tmp_path / "orders.csv"
    base_order = {
        "date": "2026-11-17",
        "customer": "Alex Morgan",
        "country": "Spain",
        "product": "Desk lamp",
        "amount": "19.95",
        "status": "pending",
    }
    invalid = {**base_order, "amount": ""}
    exact_duplicate = base_order.copy()
    business_duplicate = {**base_order, "amount": "20.95", "status": "accepted"}
    write_orders_csv(source, [invalid, base_order, exact_duplicate, business_duplicate])
    engine = create_sqlite_engine(tmp_path / "orders.db")

    report = ingest_orders_csv(
        source, engine, reference_date=date(2026, 11, 18), chunk_size=1
    )

    assert report.rows_read == 4
    assert report.rows_valid == 3
    assert report.rows_rejected == 1
    assert report.rejected_by_reason == {"missing_amount": 1}
    assert report.exact_duplicates == 1
    assert report.business_duplicates == 1
    assert report.rows_inserted == 1
    with Session(engine) as session:
        order = session.scalar(select(Order))
        assert order is not None
        assert order.customer == "Alex Morgan"
        assert order.amount == Decimal("19.95")
    engine.dispose()


def test_ingestion_rejects_unexpected_csv_columns(tmp_path):
    """Check files with a missing required column fail before loading rows."""

    source = tmp_path / "wrong-columns.csv"
    source.write_text("date,customer,amount\n2026-11-17,Ada,10.00\n", encoding="utf-8")
    engine = create_sqlite_engine(tmp_path / "orders.db")
    initialize_database(engine)

    with pytest.raises(CsvIngestionError, match="CSV columns must be exactly"):
        ingest_orders_csv(source, engine, reference_date=date(2026, 11, 18))
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 0
    engine.dispose()


def test_ingestion_does_not_silently_skip_blank_lines(tmp_path):
    """Check blank physical rows are reported as invalid rather than skipped."""

    source = tmp_path / "blank-line.csv"
    source.write_text(
        "date,customer,country,product,amount,status\n"
        "\n"
        "2026-11-17,Ada,Spain,Book,10.00,pending\n",
        encoding="utf-8",
    )
    engine = create_sqlite_engine(tmp_path / "orders.db")

    report = ingest_orders_csv(source, engine, reference_date=date(2026, 11, 18))

    assert report.rows_read == 2
    assert report.rows_rejected == 1
    assert report.rows_inserted == 1
    assert report.rejected_by_reason == {
        "missing_date": 1,
        "missing_customer": 1,
        "missing_country": 1,
        "missing_product": 1,
        "missing_amount": 1,
        "missing_status": 1,
    }
    engine.dispose()
