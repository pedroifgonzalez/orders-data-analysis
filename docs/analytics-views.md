# Analytical SQL views

The database creates two SQLite views during `initialize_database`. Both use
the persisted `orders` table and are safe to recreate during application startup.

## `sales_by_month_country`

Groups stored orders by calendar month (`YYYY-MM`) and country. It exposes
`month`, `country`, `order_count`, and `total_amount`, where `total_amount` is
the sum of order amounts for that month and country.

## `top_customers`

Groups stored orders by customer and exposes `customer`, `order_count`, and
`total_amount`. It returns at most ten customers ordered by total amount
descending, with customer name ascending as a deterministic tie-breaker.

Both views currently include every structurally valid order stored in the
database, regardless of its business status (`pending`, `accepted`, or
`rejected`). In this first version, the views report recorded order amounts;
they do not interpret order status as a sale outcome. Amounts are assumed to
be EUR according to the [data model](data-model.md).

SQLite's `strftime` is used to derive the monthly grouping key. The view
definitions are owned by
[`database/analytics.py`](../src/orders_data_analysis/database/analytics.py)
and are installed by `initialize_database`.
