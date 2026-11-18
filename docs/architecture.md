# Project architecture

## Purpose

Keep data generation, ingestion, persistence, and question answering independently understandable and testable. The packages communicate through small data contracts; infrastructure details should not leak into unrelated layers.

## Source layout and ownership

| Package | Responsibility | Must not own |
| --- | --- | --- |
| `generator` | Create reproducible synthetic order CSVs and configurable intentional defects. | Cleaning, persistence, API behavior, or LLM calls. |
| `ingestion` | Coordinate reading, validation, normalization, deduplication, and loading; report accepted and rejected rows. | SQL query policy or HTTP request handling. |
| `database` | Define persisted models, SQLite connections and transactions, repositories, analytical SQL views, and query validation. | CSV generation, API schemas, or provider-specific LLM code. |
| `llm` | Define the provider-neutral contract for turning a question into a candidate query. | Database connections, HTTP routing, or query execution. |
| `api` | Validate HTTP input, call application services, and shape responses and errors. | CSV processing, SQL construction, or provider-specific SDK usage. |

## Data flow

```text
generator ──writes──> source CSV ──read by──> ingestion ──persists through──> database
client ──question──> api ──question──> llm
                                      │ candidate SQL
                                      ▼
                           database.query_validation ──approved query──> database
client <──answer/result── api <──rows/result─────────────────────────────┘
```

The original CSV remains the source of record for imported text. The ingestion pipeline decides which rows are accepted into `orders` and should report rejected rows. Database writes should be transactional. Analytical queries should use the approved views and remain separate from LLM prompting and HTTP routing.

## Dependency boundaries

- `api` depends on service contracts and the `llm` interface; it should not import a vendor SDK directly.
- `llm` returns a candidate query. A separate validation step must enforce read-only access to the approved views before execution.
- `database.query_validation` validates candidate SQL before the database executes it; LLM output is always untrusted input.
- `ingestion` depends on validation and persistence interfaces, not on FastAPI.
- `generator` is independently runnable and deterministic when given the same seed and reference date.
- `database` is the only package that owns SQLite-specific connection and transaction details.
- API transport schemas and persisted data models are distinct, even if they contain similar fields.

## Testing boundaries

Mirror these responsibilities in tests: generator output and defect options; validation and duplicate handling; pipeline behavior with a temporary SQLite database; query validation; and API behavior with a mocked LLM client. Add end-to-end coverage only for the integration points that need it.

## Current scope

The package boundaries and initial `orders` model are in place. The generator, ingestion stages, remaining database schema, LLM provider, and API endpoint are not implemented. First-version assumptions for currency, dates, statuses, and duplicates are recorded in [the data-model notes](data-model.md); implementation should follow those rules.
