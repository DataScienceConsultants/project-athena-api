"""Narrow adapter around Project Athena's public unified-report API."""

import json
import logging
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol

from app.catalog_readiness import CatalogNotReadyError, validate_catalog_readiness
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class AthenaReport(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


class AthenaReportUnavailableError(RuntimeError):
    """An expected failure to load a catalog or construct its unified report."""


ReportBuilder = Callable[..., AthenaReport]


class CachedAthenaReport:
    """Minimal immutable-style adapter retaining the router-facing report contract."""

    def __init__(self, report: dict[str, Any]) -> None:
        self._report = report

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._report)


def _public_report_builder() -> ReportBuilder:
    """Resolve Athena lazily so health/version can run without catalog initialization."""
    module = import_module("src.observatory")
    return module.build_observatory_intelligence_report


class AthenaService:
    """Load a validated, precomputed unified report."""

    def __init__(
        self,
        builder: ReportBuilder | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._builder = builder
        self._settings = settings or get_settings()

    def build_report(self) -> AthenaReport:
        """Load the snapshot; never perform scientific processing in a web request."""
        try:
            catalog_as_of, event_count = validate_catalog_readiness(self._settings)
            snapshot_path = Path(self._settings.report_snapshot_path)
            with snapshot_path.open(encoding="utf-8") as snapshot_file:
                payload = json.load(
                    snapshot_file,
                    parse_constant=lambda value: (_ for _ in ()).throw(
                        ValueError(f"Invalid JSON constant: {value}")
                    ),
                )
            if not isinstance(payload, dict):
                raise ValueError("Snapshot root must be an object")
            metadata = payload.get("metadata")
            report = payload.get("report")
            if not isinstance(metadata, dict) or not isinstance(report, dict):
                raise ValueError("Snapshot must contain metadata and report objects")
            required = {
                "generated_at_utc",
                "catalog_as_of_utc",
                "source_event_count",
                "region_key",
            }
            if not required <= metadata.keys():
                raise ValueError("Snapshot metadata is incomplete")
            generated_at = datetime.fromisoformat(
                str(metadata["generated_at_utc"]).replace("Z", "+00:00")
            )
            cached_as_of = datetime.fromisoformat(
                str(metadata["catalog_as_of_utc"]).replace("Z", "+00:00")
            )
            if generated_at.tzinfo is None or cached_as_of.tzinfo is None:
                raise ValueError("Snapshot timestamps must include an offset")
            freshness_cutoff = datetime.now(UTC) - timedelta(
                hours=self._settings.catalog_freshness_hours
            )
            if generated_at.astimezone(UTC) < freshness_cutoff:
                raise ValueError("Snapshot generation timestamp is stale")
            if generated_at.astimezone(UTC) < cached_as_of.astimezone(UTC):
                raise ValueError("Snapshot generation timestamp predates catalog")
            if cached_as_of.astimezone(UTC) != catalog_as_of.astimezone(UTC):
                raise ValueError("Snapshot catalog timestamp does not match catalog")
            if type(metadata["source_event_count"]) is not int or metadata[
                "source_event_count"
            ] != event_count:
                raise ValueError("Snapshot event count does not match catalog")
            if metadata["region_key"] != self._settings.default_region_key:
                raise ValueError("Snapshot region does not match configuration")
            if snapshot_path.stat().st_mtime_ns < Path(
                self._settings.default_catalog_path
            ).stat().st_mtime_ns:
                raise ValueError("Snapshot is older than catalog")
            return CachedAthenaReport(report)
        except (
            CatalogNotReadyError,
            FileNotFoundError,
            OSError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
            ImportError,
            AttributeError,
        ) as exc:
            logger.warning("Project Athena report snapshot is unavailable: %s", exc)
            raise AthenaReportUnavailableError from exc


def get_athena_service() -> AthenaService:
    return AthenaService()
