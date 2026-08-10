"""Isolated, nonpredictive historical research artifact runner."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.bootstrap_catalog import DEFAULT_CHUNK_DAYS, configured_region, prepare_catalog
from app.build_report_snapshot import build_snapshot_payload
from app.config import Settings, get_settings

LOGGER = logging.getLogger(__name__)


def parse_date(value: str) -> datetime:
    """Parse a CLI calendar date as start-of-day UTC."""
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} must be a date in YYYY-MM-DD format") from exc
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def default_output_path(region_key: str) -> Path:
    return Path("data/research") / region_key


def _utc_string(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as output:
        json.dump(payload, output, allow_nan=False, ensure_ascii=False, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def _promote_directory(candidate: Path, destination: Path) -> None:
    """Atomically promote a complete directory and restore the previous one on failure."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix=f".{destination.name}.backup.", dir=destination.parent))
    backup.rmdir()
    had_destination = destination.exists()
    try:
        if had_destination:
            os.replace(destination, backup)
        os.replace(candidate, destination)
    except BaseException:
        if destination.exists():
            shutil.rmtree(destination)
        if had_destination and backup.exists():
            os.replace(backup, destination)
        raise
    finally:
        if backup.exists():
            shutil.rmtree(backup)


def run_research(
    *,
    region_key: str,
    start: datetime,
    end: datetime,
    output_dir: Path | None = None,
    minimum_magnitude: float | None = None,
    chunk_days: int = DEFAULT_CHUNK_DAYS,
    settings: Settings | None = None,
    client: Any = None,
    report_builder: Any = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Generate and atomically promote a complete set of isolated research artifacts."""
    if start >= end:
        raise ValueError("Research start must be earlier than research end")
    if chunk_days <= 0:
        raise ValueError("chunk-days must be greater than zero")
    if minimum_magnitude is not None and minimum_magnitude < 0:
        raise ValueError("minimum-magnitude must be nonnegative")

    region = configured_region(region_key)
    production = settings or get_settings()
    destination = output_dir or default_output_path(region_key)
    artifacts = {
        destination / name
        for name in ("catalog.csv", "observatory_report.json", "timeseries.json", "metadata.json")
    }
    protected = {
        Path(production.default_catalog_path).resolve(),
        Path(production.report_snapshot_path).resolve(),
    }
    if {path.resolve() for path in artifacts} & protected:
        raise ValueError("Research output would overwrite a production artifact")

    destination.parent.mkdir(parents=True, exist_ok=True)
    candidate = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.candidate.", dir=destination.parent)
    )
    try:
        research_settings = replace(
            production,
            default_region_key=region_key,
            default_catalog_path=str(candidate / "catalog.csv"),
            report_snapshot_path=str(candidate / "observatory_report.json"),
        )
        magnitude = (
            float(region["default_minimum_magnitude"])
            if minimum_magnitude is None
            else minimum_magnitude
        )
        _, _, event_count = prepare_catalog(
            research_settings,
            client=client,
            date_range=(start, end),
            minimum_magnitude=magnitude,
            chunk_days=chunk_days,
            log_prefix="Research catalog chunk",
        )
        snapshot = build_snapshot_payload(
            research_settings,
            catalog_path=candidate / "catalog.csv",
            builder=report_builder,
            generated_at=generated_at,
        )
        report = snapshot["report"]
        time_series = report["time_series"]
        _write_json(candidate / "observatory_report.json", report)
        _write_json(candidate / "timeseries.json", time_series)
        metadata = {
            "region_key": region_key,
            "region_name": region["name"],
            "start_utc": _utc_string(start),
            "end_utc": _utc_string(end),
            "generated_at_utc": snapshot["metadata"]["generated_at_utc"],
            "source": "USGS",
            "minimum_magnitude": magnitude,
            "bounds": region["bounds"],
            "event_count": event_count,
            "timeseries_period_count": len(time_series["anomaly_results"]),
            "athena_mode": "research",
            "report_is_nonpredictive": True,
        }
        _write_json(candidate / "metadata.json", metadata)
        _promote_directory(candidate, destination)
        return metadata
    finally:
        if candidate.exists():
            shutil.rmtree(candidate)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate isolated Athena artifacts for historical descriptive research. "
            "Results describe observed anomaly behavior and are nonpredictive. Dates form "
            "a half-open UTC interval [start, end)."
        )
    )
    parser.add_argument("--region", required=True, help="Configured research region key")
    parser.add_argument(
        "--start", required=True, type=parse_date, help="Start date (YYYY-MM-DD, inclusive)"
    )
    parser.add_argument(
        "--end", required=True, type=parse_date, help="End date (YYYY-MM-DD, exclusive)"
    )
    parser.add_argument(
        "--output", type=Path, help="Artifact directory (default: data/research/<region>)"
    )
    parser.add_argument(
        "--minimum-magnitude", type=float, help="Override the region's explicit USGS threshold"
    )
    parser.add_argument(
        "--chunk-days",
        type=int,
        default=DEFAULT_CHUNK_DAYS,
        help="USGS request width in days (default: 365)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run_research(
            region_key=args.region,
            start=args.start,
            end=args.end,
            output_dir=args.output,
            minimum_magnitude=args.minimum_magnitude,
            chunk_days=args.chunk_days,
        )
    except Exception as exc:
        parser.exit(1, f"Research run failed: {exc}\n")


if __name__ == "__main__":
    main()
