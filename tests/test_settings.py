"""Coverage for validated shared runtime settings."""

import pytest

from orders_data_analysis.settings import Settings


def test_settings_load_runtime_paths_limits_and_hide_api_key(monkeypatch):
    """Check environment overrides are parsed and secret keys stay out of repr."""

    monkeypatch.setenv("ORDERS_DATABASE_PATH", "tmp/orders.db")
    monkeypatch.setenv("ORDERS_CSV_PATH", "tmp/orders.csv")
    monkeypatch.setenv("QUERY_MAX_ROWS", "25")
    monkeypatch.setenv("QUERY_TIMEOUT_SECONDS", "1.5")
    monkeypatch.setenv("LLM_API_KEY", "private-test-token")

    settings = Settings.from_environment()

    assert str(settings.database_path) == "tmp/orders.db"
    assert str(settings.csv_path) == "tmp/orders.csv"
    assert settings.query_max_rows == 25
    assert settings.query_timeout_seconds == 1.5
    assert "private-test-token" not in repr(settings)


def test_settings_reject_non_positive_query_limit(monkeypatch):
    """Check invalid row limits fail early with a named setting."""

    monkeypatch.setenv("QUERY_MAX_ROWS", "0")

    with pytest.raises(ValueError, match="QUERY_MAX_ROWS"):
        Settings.from_environment()
