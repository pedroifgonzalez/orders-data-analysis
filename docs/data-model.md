# Initial data model

**Status:** Draft for discussion.

The first persisted model is intentionally limited to accepted orders. The generated CSV remains the input artifact and includes the corrupt rows; rows that fail agreed validation rules will not be represented as accepted `Order` records.

## `orders`

| Column | Type | Purpose |
| --- | --- | --- |
| `id` | Integer primary key | Identifies a stored database row. It is technical metadata and is not used to decide whether two source rows are duplicates. |
| `date` | Date | Order date after parsing. |
| `customer` | Text | Customer value from the source after agreed normalization. |
| `country` | Text | Country value from the source after agreed normalization. |
| `product` | Text | Product value from the source after agreed normalization. |
| `amount` | Numeric, 12 digits and 2 decimal places | Order amount. |
| `status` | Text | Order status after agreed normalization. |

The model is defined in [`models.py`](../src/orders_data_analysis/database/models.py) with SQLAlchemy's declarative mapping. SQLAlchemy supports SQLite and other relational database dialects, while the current implementation target remains SQLite. [SQLAlchemy declarative mapping](https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html) · [SQLite dialect](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html)

## Design boundaries

- The table has only the source fields required for analysis plus the technical primary key.
- The database primary key is not a business key and is not sufficient evidence for duplicate detection.
- There is no source order identifier in the given input fields. An identifier may be useful as additional evidence, but it would not alone decide whether a row is a duplicate.
- No customer or product lookup tables are introduced yet; names and labels are not guaranteed unique identities.
- No ingestion-batch or issue tables are introduced in this draft. The CSV remains available as the original input while validation and rejection reporting are designed.

## Agreed first-version assumptions

These are the initial business assumptions for the generator and ingestion rules. They can be revised if the project needs different behavior.

- The generated CSV will contain **1,000 data rows total**, including invalid rows and inserted duplicates.

### When an order is valid

A source row can be stored as an `Order` when all six source fields are present, its date can be parsed and is not in the future, its amount is numeric, its status is one of the canonical values below, and it is not a duplicate under the rules in this document. Missing text fields are blank after trimming whitespace. Negative and zero amounts remain allowed for now because no contrary business rule has been agreed.

### Amount and currency

- All generated order amounts are assumed to be in **EUR**.
- The CSV and `orders` table do not get a currency column for this first version.
- A missing or non-numeric amount is invalid and must not be imputed. The row is not inserted into the accepted `orders` table.
- Negative and zero amounts are still open questions; they are not rejected by an agreed rule yet.

### Dates

- A malformed, incomplete, or impossible calendar date is invalid.
- An order date later than the UTC calendar date at the start of ingestion is invalid. Capture that reference date once per file so every row in the same run is evaluated consistently.
- Dates are date-only values; there is no time-of-day or timezone in the source schema.

### Status

The canonical order status values are lowercase English words:

- `pending`
- `accepted`
- `rejected`

This is the business status of an order, not the ingestion outcome. A row with status `rejected` may still be structurally valid and stored; a malformed row is excluded regardless of its business status.

### Duplicate handling

- Exact duplicate source rows are dropped.
- Two rows are also considered duplicates when they have the same normalized customer, calendar date, and product. The assumption is that one customer cannot buy the same product twice on the same day.
- For duplicate comparison, trim surrounding whitespace and compare customer and product without case distinctions.
- Among eligible rows, keep the earliest source row and drop later matches. Rows that already fail required-field, date, amount, or status validation are rejected before deduplication and cannot suppress a valid row.
- The database `id` remains only a technical primary key. It is not part of the duplicate decision.

This rule is deliberately stricter than exact-row matching: it will drop a second legitimate purchase of the same product by the same customer on the same day. That is accepted as a first-version business assumption.
