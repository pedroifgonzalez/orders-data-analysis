# CSV ingestion

## Flow

`ingest_orders_csv(source_path, engine, ...)` reads a CSV and returns an `IngestionReport` without storing rejected rows in the `orders` table.

1. Check that the file has exactly the six expected columns.
2. Read bounded Pandas chunks (10,000 rows by default) as strings, with default NA coercion and blank-line skipping disabled so missing and malformed input remains inspectable.
3. Validate required fields, strict `YYYY-MM-DD` dates, the per-import UTC reference date, finite amounts representable by `Numeric(12, 2)`, and canonical order statuses.
4. Reject invalid rows and collect counts by reason. A row with several problems is rejected once, while each applicable reason is counted.
5. Deduplicate only valid rows. Compare exact normalized row fingerprints, then the agreed business key: case-folded customer, date, and case-folded product.
6. Insert first occurrences in batches using SQLAlchemy and SQLite.

## Why the CSV is read this way

The reader is designed to keep the ingestion behavior predictable as files grow, while preserving enough information to apply the data rules correctly:

- **Read in chunks instead of loading the whole file.** A fixed chunk size bounds the amount of CSV data and intermediate validation state held in application memory. Increasing the file from 1,000 to hundreds of thousands of rows therefore does not require keeping every row in a Pandas `DataFrame` at once. The chunk size is configurable to tune throughput and memory use.
- **Read fields as strings first.** Automatic type inference can interpret malformed values inconsistently or turn blanks into values such as `NaN`. Keeping the raw fields as text lets validation distinguish missing, malformed, and valid input explicitly before converting dates and amounts.
- **Preserve blank lines and disable default NA conversion.** Pandas normally skips blank lines and recognizes a built-in set of strings as missing values. Disabling those behaviors makes the importer account for those source rows and apply the project's missing-value rules itself, rather than silently changing the input during parsing.
- **Validate before deduplicating.** Only rows that meet the field, date, amount, and status rules can take part in duplicate detection. An invalid early row therefore cannot cause a later valid order with the same business key to be discarded.
- **Keep duplicate state in SQLite across chunks.** Chunking means the whole dataset is not available for in-memory deduplication. A temporary SQLite table tracks keys seen in earlier chunks and in the existing `orders` table, so duplicate handling remains consistent across chunk boundaries and repeated imports without expanding the persistent model.
- **Insert valid records in batches and use one transaction per file.** Batched inserts reduce per-row database overhead. The transaction ensures that a structural CSV or database failure does not leave a partially imported file, while ordinary invalid field values are reported and skipped.

This approach bounds CSV and dataframe memory, but duplicate tracking and the all-file transaction still consume database resources that grow with the number of distinct keys and inserted rows. The current implementation has not been benchmarked at 500,000 rows; chunking is intended to avoid file-sized application memory, and performance can be measured and tuned with representative data later.

## Memory and transactions

Pandas keeps only one CSV chunk and its validation results in application memory. A temporary SQLite table stores seen business keys across chunks and is seeded from existing orders, so re-importing a file does not add the same orders again. This temporary structure does not add fields or tables to the persistent data model.

All chunks from one file are processed in a single database transaction. A database or structural CSV parsing error rolls back the file import. Cell-level problems such as a future date, missing amount, or invalid status are counted as rejected rows and do not abort other rows. Each valid record is inserted as part of a batch rather than one ORM object at a time.

## Use

The generator's default source file is `data/orders.csv`; a 1,000-row sample is checked in at that path. Regenerate it with `uv run generate-orders` (or pass `--output` to choose another path). The ingestion function accepts an explicit source path, so the default sample is imported as follows:

```python
from orders_data_analysis.database.sqlite import create_sqlite_engine
from orders_data_analysis.ingestion.pipeline import ingest_orders_csv

engine = create_sqlite_engine("data/orders.db")
report = ingest_orders_csv("data/orders.csv", engine)
print(report)
```

If `reference_date` is omitted, the UTC calendar date is captured once at the start of the import. `chunk_size` defaults to 10,000 rows and can be overridden for memory or throughput tuning. `rejected_by_reason` may sum to more than `rows_rejected` because one row can violate multiple rules.

CSV files with missing, extra, or malformed columns fail the import; they are not silently skipped. Cell-level invalid values follow the rules in [the data model](data-model.md).
