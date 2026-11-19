# Analytical SQL views

The database creates three SQLite views during `initialize_database`. They use
the persisted `orders` table and are safe to recreate during application startup.

## `sales_by_month_country`

Groups stored orders by calendar month (`YYYY-MM`) and country. It exposes
`month`, `country`, `order_count`, and `total_amount`, where `total_amount` is
the sum of order amounts for that month and country.

## `top_customers`

Groups stored orders by customer and exposes `customer`, `order_count`, and
`total_amount`. It returns at most ten customers ordered by total amount
descending, with customer name ascending as a deterministic tie-breaker.

## `products_by_month`

Groups accepted orders by calendar month (`YYYY-MM`) and product. It exposes
`month`, `product`, `order_count`, and `total_amount`. This view supports
questions such as which products were sold during a given month.

All views include only orders whose business status is `accepted`. Orders
with `pending` or `rejected` status remain stored, but are excluded from sales
and customer purchase totals. Amounts are assumed to be EUR according to the
[data model](data-model.md).

SQLite's `strftime` is used to derive the monthly grouping key. The view
definitions are dropped and recreated by
[`database/analytics.py`](../src/orders_data_analysis/database/analytics.py)
when `initialize_database` runs, so existing databases pick up changes to the
view definitions.
