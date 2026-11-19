"""Create SQLite engines and initialize the project's database schema."""

from pathlib import Path

from sqlalchemy import URL, Engine, create_engine

from orders_data_analysis.database.analytics import create_analytical_views
from orders_data_analysis.database.models import Base


def create_sqlite_engine(database_path: str | Path) -> Engine:
    """Create an engine for a SQLite file or the special ``:memory:`` database."""

    path_text = str(database_path)
    if path_text != ":memory:":
        path = Path(path_text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path_text = str(path)

    return create_engine(URL.create("sqlite", database=path_text))


def initialize_database(engine: Engine) -> None:
    """Create mapped tables and approved analytical views if missing."""

    Base.metadata.create_all(engine)
    create_analytical_views(engine)
