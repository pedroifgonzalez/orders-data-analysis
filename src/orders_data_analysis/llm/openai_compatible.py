"""Optional adapter for providers exposing OpenAI-compatible chat completions."""

from __future__ import annotations

import httpx

from orders_data_analysis.llm.client import LLMServiceError

SCHEMA_DESCRIPTION = """Available SQLite views (all include accepted orders only):
- sales_by_month_country(month TEXT, country TEXT, order_count INTEGER,
  total_amount NUMERIC): monthly totals by country.
- top_customers(customer TEXT, order_count INTEGER, total_amount NUMERIC):
  top ten customers by total accepted purchase amount.
- products_by_month(month TEXT, product TEXT, order_count INTEGER,
  total_amount NUMERIC): products sold each month and their totals.

Only query these views. Do not query the orders table. Return exactly one
SQLite SELECT statement, without markdown fences or explanations."""


class OpenAICompatibleSqlGenerator:
    """Call a compatible chat completions endpoint to produce candidate SQL."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def generate_sql(self, question: str) -> str:
        """Send the question and approved view schema to this provider."""

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Translate the user's data question into one SQLite SELECT. "
                        "Use only the schema below. Return SQL only.\n\n"
                        f"{SCHEMA_DESCRIPTION}"
                    ),
                },
                {"role": "user", "content": question},
            ],
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, transport=self.transport
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
            raise LLMServiceError(
                "The language model request failed or returned an invalid response."
            ) from error

        if not isinstance(content, str) or not content.strip():
            raise LLMServiceError("The language model returned no SQL query.")
        return content.strip()
