# Synthetic order CSV generation

## Implementation choice

The generator uses Python's standard-library `csv.DictWriter` to write named columns and a dedicated `random.Random(seed)` instance to produce deterministic data. For 1,000 rows, Pandas would add a dependency without simplifying the required output. Faker could provide more realistic names, but its output can change across library versions even when seeded; the current fixed value lists keep this example small and predictable. ([Python `csv`](https://docs.python.org/3/library/csv.html), [Pandas `to_csv`](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_csv.html), [Faker seeding](https://faker.readthedocs.io/en/master/index.html#seeding-the-generator))

## Output contract

- The default file is `data/orders.csv`.
- It contains exactly 1,000 data rows by default, including corrupted rows and duplicate rows.
- The six columns are `date`, `customer`, `country`, `product`, `amount`, and `status`.
- CSV cells are text. Valid date values use ISO `YYYY-MM-DD`; valid amounts use two decimal places and are assumed to be EUR.
- A fixed seed and `--reference-date` produce repeatable output. If the reference date is omitted, the current UTC date is used.
- The generator uses only standard-library modules; it does not connect to SQLite or apply cleaning rules.

## Intentional data-quality cases

The default 1,000-row profile includes:

- 10 exact duplicate rows.
- 10 business-duplicate rows with the same customer, date, and product but a different status.
- 10 malformed, incomplete, impossible, or missing dates.
- 10 future dates relative to the supplied reference date.
- 10 missing amounts and 10 non-numeric amounts.
- 10 missing customers, 10 missing countries, and 10 missing products.
- 10 invalid statuses, split between blank and `unknown` values.

The corrupted categories are assigned to distinct base rows. Duplicate rows copy valid source rows so the file demonstrates duplicates separately from malformed records. Negative and zero amounts are not generated because their business meaning remains undecided.

## Run it

```bash
uv run generate-orders
uv run generate-orders --output data/orders.csv --rows 1000 --seed 42 --reference-date 2026-11-18
```

`--rows` is the total number of data rows in the final file, not the number of clean rows before duplicates. The generator requires at least 100 rows to represent every defect category.

## Tests

`tests/test_csv_generator.py` checks the row count and columns, confirms CSV values are read as text while valid and invalid date/amount values are both present, and verifies exact and business duplicates.
