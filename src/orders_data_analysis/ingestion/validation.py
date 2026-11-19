"""Validate and normalize source rows against the order data contract."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from orders_data_analysis.data_contracts import CSV_COLUMNS, ORDER_STATUSES

DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
AMOUNT_QUANTUM = Decimal("0.01")
MAX_ABS_AMOUNT = Decimal("10000000000")


def validate_order_row(
    raw_values: tuple[Any, ...], reference_date: date
) -> tuple[dict[str, Any] | None, list[str]]:
    """Return normalized order fields, or issue codes for an invalid CSV row."""

    row = {
        column: str(value).strip()
        for column, value in zip(CSV_COLUMNS, raw_values, strict=True)
    }
    errors: list[str] = []
    for field, value in row.items():
        if not value:
            errors.append(f"missing_{field}")

    order_date: date | None = None
    if row["date"]:
        if not DATE_PATTERN.fullmatch(row["date"]):
            errors.append("invalid_date")
        else:
            try:
                order_date = date.fromisoformat(row["date"])
            except ValueError:
                errors.append("invalid_date")
            if order_date is not None and order_date > reference_date:
                errors.append("future_date")

    amount: Decimal | None = None
    if row["amount"]:
        try:
            amount = Decimal(row["amount"])
            if (
                not amount.is_finite()
                or amount.quantize(AMOUNT_QUANTUM) != amount
                or amount.copy_abs() >= MAX_ABS_AMOUNT
            ):
                errors.append("invalid_amount")
        except InvalidOperation:
            errors.append("invalid_amount")

    status = row["status"].casefold()
    if status and status not in ORDER_STATUSES:
        errors.append("invalid_status")

    if errors:
        return None, errors

    assert order_date is not None
    assert amount is not None
    return {
        "date": order_date,
        "customer": row["customer"],
        "country": row["country"],
        "product": row["product"],
        "amount": amount,
        "status": status,
    }, []
