"""Shared source-data contract used by CSV generation and ingestion."""

CSV_COLUMNS = ("date", "customer", "country", "product", "amount", "status")
ORDER_STATUSES = ("pending", "accepted", "rejected")
