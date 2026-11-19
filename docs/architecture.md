# Project architecture

## Purpose

Keep data generation, ingestion, persistence, and question answering independently understandable and testable. The packages communicate through small data contracts; infrastructure details should not leak into unrelated layers.

## Source layout and ownership

| Package | Responsibility | Must not own |
| --- | --- | --- |
| `generator` | Create reproducible synthetic order CSVs and configurable intentional defects. | Cleaning, persistence, API behavior, or LLM calls. |
| `ingestion` | Read CSV files in bounded chunks, validate and normalize rows, deduplicate valid orders, and batch-load them; return an import report. | SQL query policy or HTTP request handling. |
| `database` | Define persisted models, SQLite connections and transactions, repositories, analytical SQL views, and query validation. | CSV generation, API schemas, or provider-specific LLM code. |
| `llm` | Define the provider-neutral contract and call a configurable OpenAI-compatible endpoint for candidate SQL. | Database connections, HTTP routing, or query execution. |
| `api` | Validate HTTP input, coordinate question-to-query flow, and shape responses and errors. | CSV processing, SQL validation/execution, or provider-specific request logic. |

## Data flow

```text
generator ──writes──> source CSV ──read by──> ingestion ──persists through──> database
client ──question──> api ──question──> llm
                                      │ candidate SQL
                                      ▼
                           database.query_validation ──approved query──> database
client <──answer/result── api <──rows/result─────────────────────────────┘
```

The original CSV remains the source of record for imported text. The ingestion pipeline validates each row before checking duplicates, and returns counts for valid, rejected, and duplicate rows. It reads bounded Pandas chunks, tracks deduplication keys in temporary SQLite storage across chunks, and inserts accepted orders in batches. One file import is one transaction. For questions, the API sends the question and approved view schema to the LLM, validates its candidate SQL, then executes it with SQLite read-only authorization and bounded time and output.

## Dependency boundaries

- `api` depends on the `llm` interface and database query service; it does not construct SQL or import a vendor SDK directly.
- `llm` returns a candidate query. A separate validation step must enforce read-only access to the approved views before execution.
- `database.query_validation` validates and executes candidate SQL with an SQLite authorizer; LLM output is always untrusted input.
- `ingestion` depends on validation and persistence interfaces, not on FastAPI.
- `generator` is independently runnable and deterministic when given the same seed and reference date.
- `database` is the only package that owns SQLite-specific connection and transaction details.
- API transport schemas and persisted data models are distinct, even if they contain similar fields.

## Testing boundaries

Mirror these responsibilities in tests: generator output and defect options; validation and duplicate handling; pipeline behavior with a temporary SQLite database; query validation; and API behavior with a mocked LLM client. Add end-to-end coverage only for the integration points that need it.

## Current scope

The generator, CSV-to-SQLite ingestion path, analytical SQLite views, and natural-language questions API are implemented. The API accepts an injectable provider-neutral `SqlGenerator`; provider selection is explicit, and the optional OpenAI-compatible adapter is registered separately. The request and security behavior are described in [the API notes](natural-language-api.md); view definitions are in [the analytics notes](analytics-views.md), and first-version data assumptions are recorded in [the data-model notes](data-model.md).
