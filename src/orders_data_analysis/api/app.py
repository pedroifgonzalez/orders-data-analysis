"""Export the FastAPI application factory and default ASGI application."""

from orders_data_analysis.api.questions import create_app

app = create_app()

__all__ = ["app", "create_app"]
