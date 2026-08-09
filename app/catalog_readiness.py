"""Operational catalog readiness checks, separate from Athena's calculations."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from app.config import Settings


class CatalogNotReadyError(RuntimeError):
    """The configured production catalog cannot safely serve analytics."""


def validate_catalog_readiness(settings: Settings) -> tuple[datetime, int]:
    """Return catalog identity, rejecting missing, unreadable, or empty data."""
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

    newest_time = newest.to_pydatetime()
    return newest_time, len(catalog)
