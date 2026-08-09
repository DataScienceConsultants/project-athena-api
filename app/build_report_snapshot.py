"""Build and safely persist Athena's unified Observatory report."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import Settings, get_settings
from app.services.athena import ReportBuilder, _public_report_builder

LOGGER = logging.getLogger(__name__)


def catalog_identity(path: str | Path) -> tuple[datetime, int]:
    """Return the newest valid event timestamp and row count for a catalog."""
    catalog = pd.read_csv(path, usecols=["event_time_utc"])
    if catalog.empty:
        raise ValueError("Cannot snapshot an empty catalog")
    times = pd.to_datetime(catalog["event_time_utc"], utc=True, errors="coerce")
    newest = times.max()
    if pd.isna(newest):
        raise ValueError("Cannot snapshot a catalog without valid event timestamps")
    return newest.to_pydatetime(), len(catalog)


def _utc_string(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def build_snapshot_payload(
    settings: Settings,
    *,
    catalog_path: str | Path | None = None,
    builder: ReportBuilder | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the report through Athena and wrap it in catalog identity metadata."""
    source = Path(catalog_path or settings.default_catalog_path)
    catalog_as_of, event_count = catalog_identity(source)
    report = (builder or _public_report_builder())(
        region_key=settings.default_region_key,
        catalog_path=str(source),
    )
    return {
        "metadata": {
            "generated_at_utc": _utc_string(generated_at or datetime.now(UTC)),
            "catalog_as_of_utc": _utc_string(catalog_as_of),
            "source_event_count": event_count,
            "region_key": settings.default_region_key,
        },
        "report": report.to_dict(),
    }


def write_snapshot_atomic(payload: dict[str, Any], destination: str | Path) -> int:
    """Strictly encode and atomically replace a snapshot, preserving old data on failure."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".json",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(
                payload,
                temporary,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            temporary.flush()
            os.fsync(temporary.fileno())
        size = temporary_path.stat().st_size
        os.replace(temporary_path, path)
        return size
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def build_report_snapshot(
    settings: Settings | None = None,
    *,
    catalog_path: str | Path | None = None,
    destination: str | Path | None = None,
    builder: ReportBuilder | None = None,
) -> dict[str, Any]:
    """Build and atomically write one configured report snapshot."""
    selected = settings or get_settings()
    source = Path(catalog_path or selected.default_catalog_path)
    target = Path(destination or selected.report_snapshot_path)
    payload = build_snapshot_payload(selected, catalog_path=source, builder=builder)
    size = write_snapshot_atomic(payload, target)
    metadata = payload["metadata"]
    LOGGER.info(
        "Report snapshot prepared: %s; catalog as of %s; %s events; %s bytes",
        target,
        metadata["catalog_as_of_utc"],
        metadata["source_event_count"],
        size,
    )
    return payload


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        build_report_snapshot()
    except Exception as exc:  # CLI boundary: all build failures must be nonzero.
        LOGGER.error("Report snapshot preparation failed: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
