from datetime import UTC, datetime

import pytest

from app.bootstrap_catalog import prepare_catalog
from app.config import Settings

NOW = datetime(2026, 8, 3, 12, tzinfo=UTC)


class FakeClient:
    def fetch(self, query):
        event_time = int((query.end_time.timestamp() - 3600) * 1000)
        return [
            {
                "id": "pr-real-1",
                "properties": {
                    "time": event_time,
                    "updated": event_time,
                    "mag": 2.1,
                    "magType": "md",
                    "place": "Puerto Rico region",
                    "type": "earthquake",
                },
                "geometry": {"coordinates": [-66.2, 18.1, 10.0]},
            }
        ]


class FailingClient:
    def fetch(self, query):
        raise RuntimeError("download failed")


def _settings(path) -> Settings:
    return Settings(default_catalog_path=str(path))


def test_successful_bootstrap_uses_athena_pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv("ATHENA_BOOTSTRAP_LOOKBACK_DAYS", "30")
    path = tmp_path / "catalog.csv"
    start, end, count = prepare_catalog(_settings(path), client=FakeClient(), now=NOW)
    assert (end - start).days == 30
    assert count == 1
    contents = path.read_text(encoding="utf-8")
    assert "event_time_utc" in contents
    assert "pr-real-1" in contents


def test_download_failure_is_propagated(monkeypatch, tmp_path):
    monkeypatch.setenv("ATHENA_BOOTSTRAP_LOOKBACK_DAYS", "30")
    with pytest.raises(RuntimeError, match="download failed"):
        prepare_catalog(_settings(tmp_path / "catalog.csv"), client=FailingClient(), now=NOW)


def test_failure_atomically_preserves_existing_catalog(monkeypatch, tmp_path):
    monkeypatch.setenv("ATHENA_BOOTSTRAP_LOOKBACK_DAYS", "30")
    path = tmp_path / "catalog.csv"
    path.write_text("existing production catalog", encoding="utf-8")
    with pytest.raises(RuntimeError):
        prepare_catalog(_settings(path), client=FailingClient(), now=NOW)
    assert path.read_text(encoding="utf-8") == "existing production catalog"
