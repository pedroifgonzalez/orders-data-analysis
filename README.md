# Orders Data Analysis

## Contents

- [Given task](#given-task)
  - [Data ingestion and cleaning](#1-data-ingestion-and-cleaning)
  - [SQL models](#2-sql-models)
  - [Natural-language API](#3-natural-language-api)
  - [Tests](#4-tests)
  - [Project decisions and reflection](#project-decisions-and-reflection)
  - [LLM and credentials](#llm-and-credentials)
  - [Delivery](#delivery)
- [How this project is built](#how-this-project-is-built)

---

## Given task

Build a small Python project that ingests, cleans, stores, and analyzes order data, then answers questions about it through a natural-language API.

## Requirements

### 1. Data ingestion and cleaning

- Generate a CSV containing at least **1,000 orders**.
- Include these fields: date, customer, country, product, amount, and status.
- Include intentional data-quality issues: duplicate rows, malformed dates, and missing amounts.
- Write a script that cleans the data and saves it to **PostgreSQL, SQLite, or DuckDB**.

### 2. SQL models

Create two SQL views:

1. Sales by month and country.
2. The top 10 customers by purchase amount.

### 3. Natural-language API

Use **FastAPI** to expose an endpoint that accepts a natural-language question, such as:

> How much did we sell in Spain in March?

The endpoint must use an LLM to translate the question into a query. Before execution, validate that the query is read-only and accesses only permitted tables. Return a clear error if the LLM fails or produces an invalid query.

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
- How AI was used: what you asked it, what suggestions you accepted, and what you corrected.

## LLM and credentials

Any LLM provider may be used, including OpenAI, Claude, Gemini, or a local model. **Do not commit API keys or other secrets to the repository.**

## Delivery

- Make commits as you work so the progress and thought process are visible. A single commit containing the entire project is not acceptable.
- Submit a link to a public GitHub repository within **48 hours** and report how long the work took.
- If the submission is successful, a 30-minute meeting will be scheduled.

## How this project is built

See [`docs/`](docs/README.md) for the project's technical decisions, including [commit conventions](docs/technical-decisions/commit-conventions.md) and [pre-commit hooks](docs/technical-decisions/pre-commit-hooks.md).
