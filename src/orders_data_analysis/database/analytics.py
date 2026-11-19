"""Create and query the approved analytical sales views."""

from sqlalchemy import Engine, text


def create_analytical_views(engine: Engine) -> None:
    """Create or refresh monthly sales and top-customer views.

    Both views include only orders whose business status is ``accepted``.
    """

    statements = (
        "DROP VIEW IF EXISTS sales_by_month_country",
        "DROP VIEW IF EXISTS top_customers",
        """
        CREATE VIEW sales_by_month_country AS
        SELECT
            strftime('%Y-%m', date) AS month,
            country,
            COUNT(*) AS order_count,
            ROUND(SUM(amount), 2) AS total_amount
        FROM orders
        WHERE status = 'accepted'
        GROUP BY strftime('%Y-%m', date), country
        """,
        """
        CREATE VIEW top_customers AS
        SELECT
            customer,
            COUNT(*) AS order_count,
            ROUND(SUM(amount), 2) AS total_amount
        FROM orders
        WHERE status = 'accepted'
        GROUP BY customer
        ORDER BY total_amount DESC, customer ASC
        LIMIT 10
        """,
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
