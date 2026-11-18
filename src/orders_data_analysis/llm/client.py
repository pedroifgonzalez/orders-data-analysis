"""Declare the LLM client boundary consumed by the question service.

Provider-specific clients, including a future local model endpoint, belong
behind this boundary so API code does not depend on a vendor or deployment.
"""
