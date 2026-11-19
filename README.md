# Orders Data Analysis

## Contents

- [Given task](#given-task)
  - [Requirements](#requirements)
    - [Data ingestion and cleaning](#1-data-ingestion-and-cleaning)
    - [SQL models](#2-sql-models)
    - [Natural-language API](#3-natural-language-api)
    - [Tests](#4-tests)
  - [Project decisions and reflection](#project-decisions-and-reflection)
  - [LLM and credentials](#llm-and-credentials)
  - [Delivery](#delivery)
- [Run locally](#run-locally)
- [Implementation decisions](#implementation-decisions)
- [What I would improve with more time](#what-i-would-improve-with-more-time)
- [How I used AI](#how-i-used-ai)
- [Tests](#tests)
- [Project documentation](#project-documentation)

## Given task

Build a Python project that generates and cleans order data, stores valid
orders in a database, provides SQL analytics, and answers natural-language
questions through an API. The sample CSV includes intentional data defects so
the ingestion flow can demonstrate validation and duplicate handling.

## Requirements

### 1. Data ingestion and cleaning

- Generate a CSV containing at least **1,000 orders**.
- Include these fields: date, customer, country, product, amount, and status.
- Include intentional data-quality issues: duplicate rows, malformed dates,
  and missing amounts.
- Write a script that cleans the data and saves it to **PostgreSQL, SQLite, or
  DuckDB**.

### 2. SQL models

Create analytical SQL views:

1. Sales by month and country.
2. The top 10 customers by purchase amount.
3. Products sold by month.

### 3. Natural-language API

Use **FastAPI** to expose an endpoint that accepts a natural-language question,
such as:

> How much did we sell in Spain in March?

The endpoint must use an LLM to translate the question into a query. Before
execution, validate that the query is read-only and accesses only permitted
tables. Return a clear error if the LLM fails or produces an invalid query.

### 4. Tests

Include at least three pytest tests covering:

- Data cleaning.
- Query validation.
- The API endpoint with a mocked LLM.

## Project decisions and reflection

Document:

- How to run the project.
- The decisions made during implementation.
- What could be improved with more time.
- How AI was used: what you asked it, what suggestions you accepted, and what
  you corrected.

These points are covered in the sections below.

## LLM and credentials

Any LLM provider may be used, including OpenAI, Claude, Gemini, or a local
model. **Do not commit API keys or other secrets to the repository.** This
implementation currently includes an OpenAI-compatible adapter; the API uses
a provider-neutral interface for future adapters.

## Delivery

- Make commits as you work so the progress and thought process are visible. A
  single commit containing the entire project is not acceptable.
- Submit a link to a public GitHub repository within **48 hours** and report
  how long the work took.
- If the submission is successful, a 30-minute meeting will be scheduled.

## Run locally

Install dependencies and load the checked-in sample CSV into SQLite:

```bash
uv sync
uv run ingest-orders
```

The importer defaults to `data/orders.csv` and `data/orders.db`. It validates
and deduplicates rows through the ingestion pipeline, then reports inserted,
rejected, and duplicate counts. To regenerate the sample first, run
`uv run generate-orders`.

Configure the OpenAI-compatible LLM adapter. Keep the key in your shell or a
secret manager; do not add it to the repository:

```bash
read -rsp "OpenAI API key: " LLM_API_KEY
printf '\n'
export LLM_API_KEY
export LLM_PROVIDER="openai-compatible"
export LLM_MODEL="gpt-6.1-terra"
```

Start the API:

```bash
uv run uvicorn orders_data_analysis.api.app:app --reload
```

Check the health endpoint at `http://127.0.0.1:8000/health`. Ask a question
with:

```bash
curl -X POST http://127.0.0.1:8000/questions \
  -H "Content-Type: application/json" \
  -d '{"question":"How much did we sell in Spain in March 2026?"}'
```

The API returns a short message with the tabular result. If the database has no
orders, it explains that and points to `uv run ingest-orders`. The database is
created at startup, but the CSV must be imported before questions can return
sales.

To run the test suite:

```bash
uv run pytest -q
```

The real-provider VCR test replays its sanitized cassette by default. See
[`docs/natural-language-api.md`](docs/natural-language-api.md) to record a new
interaction.

## Implementation decisions

- Split CSV generation, ingestion, database models and views, the API, and LLM
  adapters into separate packages so each part has a focused responsibility.
- Read CSV files in bounded Pandas chunks and validate rows before duplicate
  detection. Exact duplicates and repeated customer/date/product purchases
  are dropped; invalid rows are reported and skipped.
- Use SQLite for the current database and expose analytics through views for
  monthly sales by country, the top ten customers, and products sold by month.
  All views include only accepted orders.
- Keep one `orders` table for now. Customers and products remain values on an
  order instead of separate tables; the current requirements do not need the
  extra relationships or schema yet.
- Let the LLM propose SQL, then validate it in the backend. The backend permits
  read-only access to the approved views and applies row and time limits before
  returning results.
- Keep provider configuration in shared `settings.py`. Logs include request
  outcomes and timings but omit question text, generated SQL, row contents, and
  credentials.
- Record real HTTP interactions with VCR.py after removing the request body,
  authentication headers, compressed-response metadata, and unrelated
  provider fields. The sanitized cassette supports offline replay.

## What I would improve with more time

- Benchmark ingestion with larger representative CSV files, including around
  500,000 rows, and tune chunk size and database indexes from those results.
- Measure SQL-generation accuracy across a broader set of questions, countries,
  date ranges, and edge cases; keep unsafe-query checks independent of model
  output.
- Add another provider adapter and test it through the same `SqlGenerator`
  interface without changing the API safeguards.

## How I used AI

I divided the work into smaller parts and compared options before choosing an
approach. I acted as the orchestrator and kept the final decisions and control
of the project. The AI worked as an implementation operator to move through
the requested tasks faster.

We worked in a review cycle: I gave an instruction, the AI implemented it, I
reviewed and confirmed the result or provided feedback, and then we refined or
refactored the work where needed. I decided which options and changes to keep.

I asked the AI to compare CSV-generation options, help define order validity
and duplicate rules, propose module boundaries, implement chunked ingestion,
design guarded natural-language SQL, and set up real HTTP recordings with
VCR.py.

I accepted the bounded Pandas reader, SQLite batch insertion, separate
provider-neutral LLM interface, read-only SQL validation, and sanitized VCR
recording. I corrected the design when an ID-only duplicate rule was
insufficient, specified that only accepted orders count as sales, kept the
order model independent from the pipeline, and chose to return query results
without a second LLM call. I also used provider errors and test failures to
guide changes, including removing an unsupported `temperature` parameter and
making the empty-result response explain how to load data.

## Tests

The suite covers CSV generation and ingestion, database views, SQL validation,
API behavior with a mocked LLM, shared settings, the ingestion command, and
offline replay of a real sanitized provider interaction.

## Project documentation

See [`docs/`](docs/README.md) for the architecture, data rules, ingestion
design, natural-language API, commit conventions, and pre-commit checks.
