"""Bootstrap a real Puerto Rico catalog through Project Athena's public APIs."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings

LOGGER = logging.getLogger(__name__)
DEFAULT_LOOKBACK_DAYS = 3650
DEFAULT_CHUNK_DAYS = 365


def _parse_time(value: str, variable: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{variable} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{variable} must include a UTC offset")
    return parsed.astimezone(UTC)


def bootstrap_dates(*, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Resolve an explicit UTC range or a lookback ending now."""
    end = (
        _parse_time(os.environ["ATHENA_BOOTSTRAP_END_UTC"], "ATHENA_BOOTSTRAP_END_UTC")
        if os.getenv("ATHENA_BOOTSTRAP_END_UTC")
        else (now or datetime.now(UTC))
    )
    if os.getenv("ATHENA_BOOTSTRAP_START_UTC"):
        start = _parse_time(os.environ["ATHENA_BOOTSTRAP_START_UTC"], "ATHENA_BOOTSTRAP_START_UTC")
    else:
        days = int(os.getenv("ATHENA_BOOTSTRAP_LOOKBACK_DAYS", str(DEFAULT_LOOKBACK_DAYS)))
        if days <= 0:
            raise ValueError("ATHENA_BOOTSTRAP_LOOKBACK_DAYS must be greater than zero")
        start = end - timedelta(days=days)
    if start >= end:
        raise ValueError("Bootstrap start must be earlier than bootstrap end")
    return start, end


def bootstrap_chunks(start: datetime, end: datetime) -> tuple[tuple[datetime, datetime], ...]:
    """Return deterministic, consecutive half-open ranges for the bootstrap interval."""
    raw_chunk_days = os.getenv("ATHENA_BOOTSTRAP_CHUNK_DAYS", str(DEFAULT_CHUNK_DAYS))
    try:
        chunk_days = int(raw_chunk_days)
    except ValueError as exc:
        raise ValueError("ATHENA_BOOTSTRAP_CHUNK_DAYS must be a positive integer") from exc
    if chunk_days <= 0:
        raise ValueError("ATHENA_BOOTSTRAP_CHUNK_DAYS must be greater than zero")

    chunks: list[tuple[datetime, datetime]] = []
    chunk_start = start.astimezone(UTC)
    interval_end = end.astimezone(UTC)
    width = timedelta(days=chunk_days)
    while chunk_start < interval_end:
        chunk_end = min(chunk_start + width, interval_end)
        chunks.append((chunk_start, chunk_end))
        chunk_start = chunk_end
    return tuple(chunks)


def _region(region_key: str) -> dict[str, Any]:
    configuration = json.loads(Path("config/regions.json").read_text(encoding="utf-8"))
    try:
        return configuration["regions"][region_key]
    except (KeyError, TypeError) as exc:
        raise ValueError(f'Configured region "{region_key}" was not found') from exc


def prepare_catalog(
    settings: Settings | None = None,
    *,
    client: Any = None,
    now: datetime | None = None,
) -> tuple[datetime, datetime, int]:
    """Download with Athena, then atomically replace the production catalog."""
    from src.catalog import (
        CatalogIngestionResult,
        CatalogQuery,
        GeographicBounds,
        IngestionSummary,
        export_csv,
        ingest_historical_catalog,
    )
    from src.catalog.normalization import deduplicate_events

    selected = settings or get_settings()
    start, end = bootstrap_dates(now=now)
    region = _region(selected.default_region_key)
    bounds = GeographicBounds(**region["bounds"])
    minimum_magnitude = float(region["default_minimum_magnitude"])
    events = []
    summaries = []
    for chunk_start, chunk_end in bootstrap_chunks(start, end):
        query = CatalogQuery(
            start_time=chunk_start,
            end_time=chunk_end,
            bounds=bounds,
            minimum_magnitude=minimum_magnitude,
        )
        try:
            chunk_result = ingest_historical_catalog(query, client=client)
        except Exception as exc:
            raise RuntimeError(
                "Catalog ingestion failed for chunk "
                f"{chunk_start.isoformat()} to {chunk_end.isoformat()}"
            ) from exc
        events.extend(chunk_result.events)
        summaries.append(chunk_result.summary)
        LOGGER.info(
            "Catalog chunk: %s to %s; %s events",
            chunk_start.isoformat(),
            chunk_end.isoformat(),
            len(chunk_result.events),
        )

    deduplicated, cross_chunk_duplicates = deduplicate_events(events)
    if not deduplicated:
        raise ValueError("Athena returned an empty catalog; existing catalog was preserved")

    result = CatalogIngestionResult(
        events=tuple(deduplicated),
        summary=IngestionSummary(
            requested_count=sum(summary.requested_count for summary in summaries),
            accepted_count=sum(summary.accepted_count for summary in summaries),
            excluded_incomplete_count=sum(
                summary.excluded_incomplete_count for summary in summaries
            ),
            excluded_invalid_count=sum(summary.excluded_invalid_count for summary in summaries),
            duplicate_count=(
                sum(summary.duplicate_count for summary in summaries) + cross_chunk_duplicates
            ),
            final_count=len(deduplicated),
            start_time=start,
            end_time=end,
            minimum_magnitude=minimum_magnitude,
            bounds=bounds,
            source="USGS",
        ),
    )

    destination = Path(selected.default_catalog_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.", suffix=".csv", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        export_csv(result, temporary_path)

        # Athena's Observatory currently consumes its established catalog column names.
        import pandas as pd

        catalog = pd.read_csv(temporary_path)
        catalog = catalog.rename(
            columns={
                "time": "event_time_utc",
                "updated_time": "updated_time_utc",
                "depth": "depth_km",
            }
        )
        catalog.to_csv(temporary_path, index=False)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    LOGGER.info(
        "Catalog prepared: %s to %s; %s events",
        start.isoformat(),
        end.isoformat(),
        len(result.events),
    )
    return start, end, len(result.events)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        prepare_catalog()
    except Exception as exc:  # CLI boundary: every preparation failure must be nonzero.
        LOGGER.error("Catalog preparation failed: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
