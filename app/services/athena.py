"""Narrow adapter around Project Athena's public unified-report API."""

import logging
from collections.abc import Callable
from importlib import import_module
from typing import Any, Protocol

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class AthenaReport(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


class AthenaReportUnavailableError(RuntimeError):
    """An expected failure to load a catalog or construct its unified report."""


ReportBuilder = Callable[..., AthenaReport]


def _public_report_builder() -> ReportBuilder:
    """Resolve Athena lazily so health/version can run without catalog initialization."""
    module = import_module("project_athena.observatory")
    return module.build_observatory_intelligence_report


class AthenaService:
    """Build exactly one unified report per service invocation."""

    def __init__(
        self,
        builder: ReportBuilder | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._builder = builder
        self._settings = settings or get_settings()

    def build_report(self) -> AthenaReport:
        """Delegate scientific processing to Athena and normalize expected failures."""
        try:
            builder = self._builder or _public_report_builder()
            return builder(
                region_key=self._settings.default_region_key,
                catalog_path=self._settings.default_catalog_path,
            )
        except (FileNotFoundError, OSError, ValueError, ImportError, AttributeError) as exc:
            logger.exception("Project Athena could not build the unified report")
            raise AthenaReportUnavailableError from exc


def get_athena_service() -> AthenaService:
    return AthenaService()
