from datetime import UTC, datetime

import pytest

from app.catalog_readiness import CatalogNotReadyError, validate_catalog_readiness
from app.config import Settings


def _settings(path) -> Settings:
    return Settings(default_catalog_path=str(path), catalog_freshness_hours=72)


def test_missing_catalog_is_not_ready(tmp_path):
    with pytest.raises(CatalogNotReadyError, match="missing"):
        validate_catalog_readiness(_settings(tmp_path / "missing.csv"))


def test_empty_catalog_is_not_ready(tmp_path):
    path = tmp_path / "catalog.csv"
    path.write_text("event_time_utc\n", encoding="utf-8")
    with pytest.raises(CatalogNotReadyError, match="empty"):
        validate_catalog_readiness(_settings(path))


def test_old_newest_event_is_valid_catalog_identity(tmp_path):
    path = tmp_path / "catalog.csv"
    path.write_text("event_time_utc\n2026-07-01T00:00:00Z\n", encoding="utf-8")
    newest, count = validate_catalog_readiness(_settings(path))
    assert newest == datetime(2026, 7, 1, tzinfo=UTC)
    assert count == 1


def test_fresh_catalog_is_ready(tmp_path):
    path = tmp_path / "catalog.csv"
    path.write_text("event_time_utc\n2026-08-02T00:00:00Z\n", encoding="utf-8")
    newest, count = validate_catalog_readiness(_settings(path))
    assert newest == datetime(2026, 8, 2, tzinfo=UTC)
    assert count == 1


def test_synthetic_fixture_is_not_the_production_default():
    assert Settings().default_catalog_path == "data/catalog.csv"
    assert Settings().default_catalog_path != "tests/fixtures/catalog.csv"
