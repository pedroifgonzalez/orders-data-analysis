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
            "order_count": 2,
            "total_amount": 0.3,
        },
        {
            "month": "2026-01",
            "country": "Spain",
            "order_count": 1,
            "total_amount": 10,
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
    assert rows[0]["total_amount"] == 12
    assert rows[0]["order_count"] == 1
    assert rows[-1]["customer"] == "Customer 02"
    assert rows[-1]["total_amount"] == 3
    engine.dispose()


def test_products_by_month_view_lists_only_accepted_products_for_month(tmp_path):
    """Check monthly product totals include accepted orders and exclude others."""

    engine = create_sqlite_engine(tmp_path / "analytics.db")
    initialize_database(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Order(
                    date=date(2026, 3, 1),
                    customer="Ada",
                    country="Spain",
                    product="Notebook",
                    amount=Decimal("12.50"),
                    status="accepted",
                ),
                Order(
                    date=date(2026, 3, 2),
                    customer="Ben",
                    country="France",
                    product="Notebook",
                    amount=Decimal("7.50"),
                    status="accepted",
                ),
                Order(
                    date=date(2026, 3, 3),
                    customer="Cy",
                    country="Spain",
                    product="Pen",
                    amount=Decimal("9.00"),
                    status="pending",
                ),
                Order(
                    date=date(2026, 4, 1),
                    customer="Dee",
                    country="Spain",
                    product="Water bottle",
                    amount=Decimal("5.00"),
                    status="accepted",
                ),
            ]
        )
        session.commit()

    with engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    "SELECT month, product, order_count, total_amount "
                    "FROM products_by_month WHERE month = '2026-03' "
                    "ORDER BY product"
                )
            )
            .mappings()
            .all()
        )

    assert rows == [
        {
            "month": "2026-03",
            "product": "Notebook",
            "order_count": 2,
            "total_amount": 20,
        }
    ]
    engine.dispose()


def test_initialize_database_can_be_called_repeatedly(tmp_path):
    """Check repeated initialization leaves all analytical views usable."""

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

    assert names == [
        "products_by_month",
        "sales_by_month_country",
        "top_customers",
    ]
    engine.dispose()


def test_initialize_database_replaces_preexisting_view_definitions(tmp_path):
    """Check initialization replaces old views so they adopt current rules."""

    engine = create_sqlite_engine(tmp_path / "analytics.db")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE orders (status TEXT, date TEXT, country TEXT, "
            "customer TEXT, product TEXT, amount NUMERIC)"
        )
        connection.exec_driver_sql(
            "CREATE VIEW top_customers AS "
            "SELECT customer, SUM(amount) AS total_amount FROM orders "
            "GROUP BY customer"
        )

    initialize_database(engine)

    with engine.connect() as connection:
        sql = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'view' AND name = 'top_customers'"
        ).scalar_one()

    assert "status = 'accepted'" in sql
    engine.dispose()
