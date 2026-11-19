"""Create and query the approved analytical sales views."""

from sqlalchemy import Engine, text


def create_analytical_views(engine: Engine) -> None:
    """Create the monthly sales and top-customer views if they do not exist.

    Both views aggregate every structurally valid order stored in ``orders``;
    order status is retained as business data and is not used as an ingestion
    outcome or as a filter for these initial reports.
    """

    statements = (
        """
        CREATE VIEW IF NOT EXISTS sales_by_month_country AS
        SELECT
            strftime('%Y-%m', date) AS month,
            country,
            COUNT(*) AS order_count,
            ROUND(SUM(amount), 2) AS total_amount
        FROM orders
        GROUP BY strftime('%Y-%m', date), country
        """,
        """
        CREATE VIEW IF NOT EXISTS top_customers AS
        SELECT
            customer,
            COUNT(*) AS order_count,
            ROUND(SUM(amount), 2) AS total_amount
        FROM orders
        GROUP BY customer
        ORDER BY total_amount DESC, customer ASC
        LIMIT 10
        """,
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
