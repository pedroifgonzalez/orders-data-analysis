"""Coverage for the supported CSV-to-SQLite command-line import."""

import csv

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from orders_data_analysis.database.models import Order
from orders_data_analysis.database.sqlite import create_sqlite_engine
from orders_data_analysis.ingestion.cli import main


def test_ingestion_cli_imports_csv_through_the_pipeline(tmp_path, capsys):
    """Check the CLI imports valid rows, deduplicates, and reports useful totals."""

    source = tmp_path / "orders.csv"
    database = tmp_path / "orders.db"
    row = ["2026-03-05", "Ada", "Spain", "Notebook", "12.50", "accepted"]
    with source.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["date", "customer", "country", "product", "amount", "status"])
        writer.writerow(row)
        writer.writerow(row)

    exit_code = main(
        [
            "--source",
            str(source),
            "--database",
            str(database),
            "--reference-date",
            "2026-03-10",
        ]
    )

    engine = create_sqlite_engine(database)
    with Session(engine) as session:
        order_count = session.scalar(select(func.count()).select_from(Order))
    engine.dispose()

    assert exit_code == 0
    assert order_count == 1
    assert "2 rows read, 1 inserted" in capsys.readouterr().out
