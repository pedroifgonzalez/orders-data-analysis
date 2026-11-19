from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from orders_data_analysis.database.models import Order
from orders_data_analysis.database.sqlite import (
    create_sqlite_engine,
    initialize_database,
)


def test_sales_by_month_country_view_aggregates_order_totals(tmp_path):
    """Check monthly sales are grouped by calendar month and country."""

    engine = create_sqlite_engine(tmp_path / "analytics.db")
    initialize_database(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Order(
                    date=date(2026, 1, 3),
                    customer="Ada",
                    country="Spain",
                    product="Book",
                    amount=Decimal("10.00"),
                    status="accepted",
                ),
                Order(
                    date=date(2026, 1, 28),
                    customer="Ben",
                    country="Spain",
                    product="Pen",
                    amount=Decimal("5.50"),
                    status="pending",
                ),
                Order(
                    date=date(2026, 1, 14),
                    customer="Cy",
                    country="France",
                    product="Book",
                    amount=Decimal("8.00"),
                    status="rejected",
                ),
                Order(
                    date=date(2026, 1, 15),
                    customer="Dee",
                    country="France",
                    product="Pen",
                    amount=Decimal("0.10"),
                    status="accepted",
                ),
                Order(
                    date=date(2026, 1, 16),
                    customer="Eli",
                    country="France",
                    product="Pencil",
                    amount=Decimal("0.20"),
                    status="accepted",
                ),
            ]
        )
        session.commit()

    with engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    "SELECT month, country, order_count, total_amount "
                    "FROM sales_by_month_country ORDER BY country"
                )
            )
            .mappings()
            .all()
        )

    assert rows == [
        {
            "month": "2026-01",
            "country": "France",
            "order_count": 3,
            "total_amount": 8.3,
        },
        {
            "month": "2026-01",
            "country": "Spain",
            "order_count": 2,
            "total_amount": 15.5,
        },
    ]
    engine.dispose()


def test_top_customers_view_returns_ten_highest_totals(tmp_path):
    """Check the customer view ranks total purchase amounts and limits ten."""

    engine = create_sqlite_engine(tmp_path / "analytics.db")
    initialize_database(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Order(
                    date=date(2026, 1, 1),
                    customer=f"Customer {index:02}",
                    country="Spain",
                    product="Book",
                    amount=Decimal(index + 1),
                    status="accepted",
                )
                for index in range(12)
            ]
        )
        session.add(
            Order(
                date=date(2026, 2, 1),
                customer="Customer 11",
                country="Spain",
                product="Pen",
                amount=Decimal("1.00"),
                status="rejected",
            )
        )
        session.commit()

    with engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    "SELECT customer, order_count, total_amount "
                    "FROM top_customers ORDER BY total_amount DESC, customer ASC"
                )
            )
            .mappings()
            .all()
        )

    assert len(rows) == 10
    assert rows[0]["customer"] == "Customer 11"
    assert rows[0]["total_amount"] == 13
    assert rows[0]["order_count"] == 2
    assert rows[-1]["customer"] == "Customer 02"
    assert rows[-1]["total_amount"] == 3
    engine.dispose()


def test_initialize_database_can_be_called_repeatedly(tmp_path):
    """Check repeated initialization leaves both analytical views usable."""

    engine = create_sqlite_engine(tmp_path / "analytics.db")

    initialize_database(engine)
    initialize_database(engine)

    with engine.connect() as connection:
        names = (
            connection.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'view' ORDER BY name"
                )
            )
            .scalars()
            .all()
        )

    assert names == ["sales_by_month_country", "top_customers"]
    engine.dispose()
