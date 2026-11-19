import csv
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from orders_data_analysis.data_contracts import CSV_COLUMNS, ORDER_STATUSES
from orders_data_analysis.generator.csv_generator import generate_orders_csv


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        rows = list(reader)
        return reader.fieldnames, rows


def test_generator_writes_exact_row_count_and_expected_columns(tmp_path):
    """Check the generated file has 1,000 records and the six required columns."""

    output = tmp_path / "orders.csv"
    reference_date = date(2026, 11, 18)

    summary = generate_orders_csv(output, seed=7, reference_date=reference_date)
    columns, rows = read_rows(output)

    assert summary.rows_written == 1_000
    assert len(rows) == 1_000
    assert tuple(columns) == CSV_COLUMNS
    assert all(isinstance(value, str) for row in rows for value in row.values())


def test_generator_includes_valid_and_invalid_field_values(tmp_path):
    """Check date, amount, and text fields contain valid and intentional bad values."""

    output = tmp_path / "orders.csv"
    reference_date = date(2026, 11, 18)
    generate_orders_csv(output, seed=7, reference_date=reference_date)
    _, rows = read_rows(output)

    parsed_dates = []
    for row in rows:
        try:
            parsed_dates.append(date.fromisoformat(row["date"]))
        except ValueError:
            continue
    assert any(order_date <= reference_date for order_date in parsed_dates)
    assert any(order_date > reference_date for order_date in parsed_dates)
    assert any(not row["date"] for row in rows)
    assert any(
        row["date"] and row["date"] not in {value.isoformat() for value in parsed_dates}
        for row in rows
    )

    parsed_amounts = []
    for row in rows:
        try:
            parsed_amounts.append(Decimal(row["amount"]))
        except (InvalidOperation, ValueError):
            continue
    assert any(amount > 0 for amount in parsed_amounts)
    assert any(not row["amount"] for row in rows)
    assert any(row["amount"] == "not-a-number" for row in rows)

    assert any(
        not row[field]
        for row in rows
        for field in ("customer", "country", "product", "status")
    )
    assert any(row["status"] == "unknown" for row in rows)
    assert any(row["status"] in ORDER_STATUSES for row in rows)


def test_generator_includes_exact_and_business_duplicates(tmp_path):
    """Check the output includes exact copies and same-customer/date/product duplicates."""

    output = tmp_path / "orders.csv"
    generate_orders_csv(output, seed=7, reference_date=date(2026, 11, 18))
    _, rows = read_rows(output)

    exact_rows = Counter(tuple(row[column] for column in CSV_COLUMNS) for row in rows)
    assert any(count > 1 for count in exact_rows.values())

    business_groups = defaultdict(list)
    for row in rows:
        key = (
            row["customer"].strip().casefold(),
            row["date"],
            row["product"].strip().casefold(),
        )
        business_groups[key].append(tuple(row[column] for column in CSV_COLUMNS))
    assert any(
        len(group) > 1 and len(set(group)) > 1 for group in business_groups.values()
    )
