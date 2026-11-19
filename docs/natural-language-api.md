# Natural-language questions API

## Request flow

`POST /questions` accepts `{"question": "..."}`. The service sends the
question and the approved view schema to an OpenAI-compatible chat completions
endpoint. The model returns SQL only. The backend validates and executes that
SQL, then returns the matching columns and rows as JSON; it does not make a
second LLM call to paraphrase the result.

The model is not given database credentials and cannot execute queries. The
backend accepts a single read-only `SELECT` that reads only
`sales_by_month_country` or `top_customers`. SQLite's authorizer also blocks
base-table reads, writes, unapproved functions, and other database operations.
Execution is limited to two seconds and 100 returned rows. The response's
`truncated` flag indicates when more rows matched than the response contains.
Sales views already include only `accepted` orders.

The application depends on the provider-neutral `SqlGenerator` interface. It
does not choose a provider implicitly. An OpenAI-compatible chat completions
adapter is included as one option; adapters for other hosted or local models
can implement the same interface without changing the API or SQL safeguards.

## Configuration and run

For the included OpenAI-compatible adapter, explicitly select the provider,
then set the model identifier and API key in the server environment. The key
can use the generic `LLM_API_KEY` name or `OPENAI_API_KEY`; `LLM_BASE_URL`
optionally selects another compatible endpoint. The default base URL is
`https://api.openai.com/v1`. The database defaults to `data/orders.db` and can
be changed with `ORDERS_DATABASE_PATH`.

```bash
export LLM_API_KEY="..."
export LLM_PROVIDER="openai-compatible"
export LLM_MODEL="your-model-name"
uv run uvicorn orders_data_analysis.api.app:app --reload
```

Then send a request to `http://127.0.0.1:8000/questions`:

```json
{"question": "How much did we sell in Spain in March 2026?"}
```

Example response:

```json
{
  "question": "How much did we sell in Spain in March 2026?",
  "columns": ["month", "country", "total_amount"],
  "rows": [
    {"month": "2026-03", "country": "Spain", "total_amount": 1250.5}
  ],
  "truncated": false
}
```

## Error responses

- `422`: the model returned SQL that is invalid, writes data, or accesses an
  unapproved table/view.
- `502`: the model endpoint failed or returned an invalid response.
- `503`: required model configuration is missing.
- `504`: the database query exceeded its time limit.

The API does not include raw SQL or provider error details in client responses.
Only the `openai-compatible` adapter is included now; selecting another
provider requires implementing its `SqlGenerator` adapter and registering it
in `llm/factory.py`. Keep API keys in environment variables or a deployment
secret store; never commit them to the repository.
