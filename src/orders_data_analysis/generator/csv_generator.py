"""Generate a reproducible order CSV with intentional data-quality defects."""

from __future__ import annotations

import argparse
import csv
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

CSV_COLUMNS = ("date", "customer", "country", "product", "amount", "status")
ORDER_STATUSES = ("pending", "accepted", "rejected")
MIN_ROW_COUNT = 100

CUSTOMERS = (
    "Alex Morgan",
    "Ana López",
    "Ava Patel",
    "Ben Carter",
    "Carlos Ruiz",
    "Chloé Martin",
    "David Kim",
    "Elena García",
    "Emma Wilson",
    "Fatima Ali",
    "Hugo Bernard",
    "Isabella Rossi",
    "James Taylor",
    "Liam O'Connor",
    "Maya Chen",
    "Noah Smith",
    "Olivia Brown",
    "Sofia Müller",
    "Theo Janssen",
    "Yuki Tanaka",
)
COUNTRIES = (
    "Austria",
    "Belgium",
    "France",
    "Germany",
    "Ireland",
    "Italy",
    "Netherlands",
    "Portugal",
    "Spain",
)
PRODUCTS = (
    "Desk lamp",
    "Headphones",
    "Keyboard",
    "Laptop stand",
    "Monitor",
    "Mouse",
    "Notebook",
    "Office chair",
    "USB hub",
    "Water bottle",
)


@dataclass(frozen=True)
class GenerationSummary:
    """Counts and destination for one generated CSV."""

    path: Path
    rows_written: int
    exact_duplicates: int
    business_duplicates: int
    corrupted_rows: int


def _make_valid_order(rng: random.Random, as_of: date) -> dict[str, str]:
    days_back = rng.randint(0, 4 * 365)
    cents = rng.randint(500, 250_000)
    amount = Decimal(cents) / Decimal(100)
    return {
        "date": (as_of - timedelta(days=days_back)).isoformat(),
        "customer": rng.choice(CUSTOMERS),
        "country": rng.choice(COUNTRIES),
        "product": rng.choice(PRODUCTS),
        "amount": f"{amount:.2f}",
        "status": rng.choice(ORDER_STATUSES),
    }


def _make_unique_orders(
    rng: random.Random, count: int, as_of: date
) -> list[dict[str, str]]:
    """Create base orders with unique customer/date/product combinations."""

    orders: list[dict[str, str]] = []
    used_business_keys: set[tuple[str, str, str]] = set()
    while len(orders) < count:
        order = _make_valid_order(rng, as_of)
        business_key = (order["customer"], order["date"], order["product"])
        if business_key not in used_business_keys:
            used_business_keys.add(business_key)
            orders.append(order)
    return orders


def _apply_data_defects(
    rows: list[dict[str, str]], indexes_by_defect: dict[str, list[int]], as_of: date
) -> None:
    malformed_dates = ("", "2026-02", "2026-02-30", "not-a-date")
    for defect, indexes in indexes_by_defect.items():
        for offset, index in enumerate(indexes):
            row = rows[index]
            if defect == "malformed_date":
                row["date"] = malformed_dates[offset % len(malformed_dates)]
            elif defect == "future_date":
                row["date"] = (as_of + timedelta(days=1 + offset)).isoformat()
            elif defect == "missing_amount":
                row["amount"] = ""
            elif defect == "nonnumeric_amount":
                row["amount"] = "not-a-number"
            elif defect == "missing_customer":
                row["customer"] = ""
            elif defect == "missing_country":
                row["country"] = ""
            elif defect == "missing_product":
                row["product"] = ""
            elif defect == "invalid_status":
                row["status"] = "" if offset % 2 else "unknown"


def generate_orders_csv(
    output_path: str | Path,
    *,
    row_count: int = 1_000,
    seed: int = 42,
    reference_date: date | None = None,
) -> GenerationSummary:
    """Write ``row_count`` order rows, including corrupt and duplicate rows.

    ``seed`` and ``reference_date`` together make the output reproducible.
    Duplicate and corruption rates are fixed for this first generator profile.
    """

    if row_count < MIN_ROW_COUNT:
        raise ValueError(f"row_count must be at least {MIN_ROW_COUNT}")

    as_of = reference_date or datetime.now(timezone.utc).date()
    rng = random.Random(seed)
    duplicate_count = max(2, round(row_count * 0.02))
    exact_duplicate_count = duplicate_count // 2
    business_duplicate_count = duplicate_count - exact_duplicate_count
    base_count = row_count - duplicate_count
    corrupted_per_type = max(1, round(row_count * 0.01))
    defect_names = (
        "malformed_date",
        "future_date",
        "missing_amount",
        "nonnumeric_amount",
        "missing_customer",
        "missing_country",
        "missing_product",
        "invalid_status",
    )
    corrupted_count = corrupted_per_type * len(defect_names)
    duplicate_source_count = exact_duplicate_count + business_duplicate_count
    if duplicate_source_count + corrupted_count > base_count:
        raise ValueError("row_count is too small for the configured defect profile")

    rows = _make_unique_orders(rng, base_count, as_of)
    indexes = list(range(base_count))
    rng.shuffle(indexes)

    exact_sources = indexes[:exact_duplicate_count]
    business_sources = indexes[
        exact_duplicate_count:duplicate_source_count
    ]
    defect_indexes = indexes[duplicate_source_count:]
    indexes_by_defect = {
        defect: defect_indexes[
            position * corrupted_per_type : (position + 1) * corrupted_per_type
        ]
        for position, defect in enumerate(defect_names)
    }
    _apply_data_defects(rows, indexes_by_defect, as_of)

    duplicates_by_source: dict[int, list[dict[str, str]]] = {}
    for source_index in exact_sources:
        duplicates_by_source.setdefault(source_index, []).append(
            rows[source_index].copy()
        )
    for source_index in business_sources:
        duplicate = rows[source_index].copy()
        current_status = duplicate["status"]
        duplicate["status"] = next(
            status for status in ORDER_STATUSES if status != current_status
        )
        duplicates_by_source.setdefault(source_index, []).append(duplicate)

    ordered_rows: list[dict[str, str]] = []
    for source_index in indexes:
        ordered_rows.append(rows[source_index])
        ordered_rows.extend(duplicates_by_source.get(source_index, ()))

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=CSV_COLUMNS,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(ordered_rows)

    return GenerationSummary(
        path=destination,
        rows_written=len(ordered_rows),
        exact_duplicates=exact_duplicate_count,
        business_duplicates=business_duplicate_count,
        corrupted_rows=corrupted_count,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point for generating the sample CSV."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/orders.csv"))
    parser.add_argument("--rows", type=int, default=1_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--reference-date",
        type=date.fromisoformat,
        help="UTC reference date in YYYY-MM-DD format; defaults to today's UTC date",
    )
    args = parser.parse_args(argv)

    summary = generate_orders_csv(
        args.output,
        row_count=args.rows,
        seed=args.seed,
        reference_date=args.reference_date,
    )
    print(
        f"Generated {summary.rows_written} rows at {summary.path} "
        f"({summary.exact_duplicates} exact duplicates, "
        f"{summary.business_duplicates} business duplicates, "
        f"{summary.corrupted_rows} corrupted rows)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
