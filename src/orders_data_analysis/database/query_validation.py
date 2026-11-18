"""Reject non-read-only queries and references outside approved SQL views.

Validate LLM-generated SQL before execution; never treat model output as trusted.
"""
