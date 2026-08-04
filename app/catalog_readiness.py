"""Operational catalog readiness checks, separate from Athena's calculations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from app.config import Settings


class CatalogNotReadyError(RuntimeError):
    """The configured production catalog cannot safely serve analytics."""


def validate_catalog_readiness(
    settings: Settings, *, now: datetime | None = None
) -> tuple[datetime, int]:
    """Return the newest event and count, or reject missing, empty, or stale data."""
    path = Path(settings.default_catalog_path)
    if not path.is_file():
        raise CatalogNotReadyError(f"Catalog is missing: {path}")

    try:
        catalog = pd.read_csv(path, usecols=["event_time_utc"])
    except (OSError, ValueError) as exc:
        raise CatalogNotReadyError(f"Catalog cannot be read: {path}") from exc
    if catalog.empty:
        raise CatalogNotReadyError(f"Catalog is empty: {path}")

    event_times = pd.to_datetime(catalog["event_time_utc"], utc=True, errors="coerce")
    newest = event_times.max()
    if pd.isna(newest):
        raise CatalogNotReadyError(f"Catalog contains no valid event timestamps: {path}")

    current_time = now or datetime.now(UTC)
    newest_time = newest.to_pydatetime()
    if newest_time < current_time - timedelta(hours=settings.catalog_freshness_hours):
        raise CatalogNotReadyError(
            f"Catalog is stale: newest event is {newest_time.isoformat()}"
        )
    return newest_time, len(catalog)
