"""Command-line entry point for importing CSV orders into SQLite."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from orders_data_analysis.database.sqlite import create_sqlite_engine
from orders_data_analysis.ingestion.pipeline import CsvIngestionError, ingest_orders_csv
from orders_data_analysis.settings import Settings, configure_logging

logger = logging.getLogger(__name__)


def _parse_date(value: str) -> date:
    """Parse the optional fixed date used to validate future order dates."""

    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "Use YYYY-MM-DD for the reference date."
        ) from error


def _build_parser(settings: Settings) -> argparse.ArgumentParser:
    """Create the import CLI with paths and batch size from shared settings."""

    parser = argparse.ArgumentParser(
        description="Validate, deduplicate, and import an orders CSV into SQLite."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=settings.csv_path,
        help=f"CSV source (default: {settings.csv_path})",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=settings.database_path,
        help=f"SQLite database (default: {settings.database_path})",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=settings.ingestion_chunk_size,
        help=f"Rows processed per batch (default: {settings.ingestion_chunk_size})",
    )
    parser.add_argument(
        "--reference-date",
        type=_parse_date,
        default=None,
        help="Optional validation date in YYYY-MM-DD format; defaults to today's UTC date.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Import a CSV and print relevant totals without logging order contents."""

    try:
        settings = Settings.from_environment()
    except ValueError as error:
        print(f"Invalid settings: {error}", file=sys.stderr)
        return 2

    configure_logging(settings)
    args = _build_parser(settings).parse_args(argv)
    if args.chunk_size < 1:
        print("--chunk-size must be a positive integer.", file=sys.stderr)
        return 2

    engine = create_sqlite_engine(args.database)
    try:
        report = ingest_orders_csv(
            args.source,
            engine,
            reference_date=args.reference_date,
            chunk_size=args.chunk_size,
        )
    except CsvIngestionError:
        logger.error("CSV ingestion rejected: invalid CSV structure or content")
        return 1
    except OSError:
        logger.error("CSV source could not be read")
        return 1
    except SQLAlchemyError as error:
        logger.error("SQLite ingestion failed (%s)", type(error).__name__)
        return 1
    finally:
        engine.dispose()

    logger.info(
        "CSV ingestion completed: read=%d inserted=%d rejected=%d "
        "exact_duplicates=%d business_duplicates=%d",
        report.rows_read,
        report.rows_inserted,
        report.rows_rejected,
        report.exact_duplicates,
        report.business_duplicates,
    )
    print(
        f"Ingestion complete: {report.rows_read} rows read, "
        f"{report.rows_inserted} inserted, {report.rows_rejected} rejected, "
        f"{report.exact_duplicates} exact duplicates and "
        f"{report.business_duplicates} business duplicates."
    )
    if report.rejected_by_reason:
        reasons = ", ".join(
            f"{reason}={count}"
            for reason, count in sorted(report.rejected_by_reason.items())
        )
        print(f"Rejected by reason: {reasons}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
