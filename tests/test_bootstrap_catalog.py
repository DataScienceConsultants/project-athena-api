from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from app.bootstrap_catalog import (
    DEFAULT_CHUNK_DAYS,
    DEFAULT_LOOKBACK_DAYS,
    bootstrap_chunks,
    bootstrap_dates,
    prepare_catalog,
)
from app.config import Settings

NOW = datetime(2026, 8, 3, 12, tzinfo=UTC)


def _feature(event_id, event_time, *, updated_time=None):
    timestamp = int(event_time.timestamp() * 1000)
    return {
        "id": event_id,
        "properties": {
            "time": timestamp,
            "updated": int((updated_time or event_time).timestamp() * 1000),
            "mag": 2.1,
            "magType": "md",
            "place": "Puerto Rico region",
            "type": "earthquake",
        },
        "geometry": {"coordinates": [-66.2, 18.1, 10.0]},
    }


class RecordingClient:
    def __init__(self, responses=None, *, fail_at=None):
        self.responses = responses or {}
        self.fail_at = fail_at
        self.queries = []

    def fetch(self, query):
        index = len(self.queries)
        self.queries.append(query)
        if index == self.fail_at:
            raise RuntimeError("download failed")
        if index in self.responses:
            return self.responses[index]
        return [_feature(f"pr-real-{index}", query.end_time - timedelta(hours=1))]


def _settings(path) -> Settings:
    return Settings(default_catalog_path=str(path))


def test_default_bootstrap_is_rolling_ten_years(monkeypatch):
    monkeypatch.delenv("ATHENA_BOOTSTRAP_LOOKBACK_DAYS", raising=False)
    monkeypatch.delenv("ATHENA_BOOTSTRAP_START_UTC", raising=False)
    monkeypatch.delenv("ATHENA_BOOTSTRAP_END_UTC", raising=False)
    start, end = bootstrap_dates(now=NOW)
    assert DEFAULT_LOOKBACK_DAYS == 3650
    assert (start, end) == (NOW - timedelta(days=3650), NOW)


def test_explicit_start_and_end_timestamps(monkeypatch):
    monkeypatch.setenv("ATHENA_BOOTSTRAP_START_UTC", "2020-01-02T03:04:05Z")
    monkeypatch.setenv("ATHENA_BOOTSTRAP_END_UTC", "2021-02-03T04:05:06+00:00")
    assert bootstrap_dates(now=NOW) == (
        datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC),
        datetime(2021, 2, 3, 4, 5, 6, tzinfo=UTC),
    )


def test_yearly_chunk_generation(monkeypatch):
    monkeypatch.delenv("ATHENA_BOOTSTRAP_CHUNK_DAYS", raising=False)
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=DEFAULT_CHUNK_DAYS * 3)
    chunks = bootstrap_chunks(start, end)
    assert chunks == tuple(
        (start + timedelta(days=365 * index), start + timedelta(days=365 * (index + 1)))
        for index in range(3)
    )


def test_partial_final_chunk_and_exact_boundaries(monkeypatch):
    monkeypatch.setenv("ATHENA_BOOTSTRAP_CHUNK_DAYS", "365")
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=800)
    chunks = bootstrap_chunks(start, end)
    assert chunks[-1] == (start + timedelta(days=730), end)
    assert chunks[0][0] == start
    assert chunks[-1][1] == end
    assert all(left[1] == right[0] for left, right in zip(chunks, chunks[1:], strict=False))


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_invalid_chunk_size_environment_variable(monkeypatch, value):
    monkeypatch.setenv("ATHENA_BOOTSTRAP_CHUNK_DAYS", value)
    with pytest.raises(ValueError, match="ATHENA_BOOTSTRAP_CHUNK_DAYS"):
        bootstrap_chunks(NOW - timedelta(days=1), NOW)


def test_empty_intermediate_chunk_is_allowed(monkeypatch, tmp_path):
    monkeypatch.setenv("ATHENA_BOOTSTRAP_LOOKBACK_DAYS", "730")
    client = RecordingClient(
        {0: [_feature("first", NOW - timedelta(days=500))], 1: []}
    )
    path = tmp_path / "catalog.csv"
    _, _, count = prepare_catalog(_settings(path), client=client, now=NOW)
    assert count == 1
    assert len(client.queries) == 2


def test_adjacent_boundary_duplicate_uses_athena_deduplication(monkeypatch, tmp_path):
    monkeypatch.setenv("ATHENA_BOOTSTRAP_LOOKBACK_DAYS", "730")
    boundary = NOW - timedelta(days=365)
    old = _feature("duplicate", boundary - timedelta(seconds=1), updated_time=boundary)
    new = _feature("duplicate", boundary, updated_time=boundary + timedelta(hours=1))
    client = RecordingClient({0: [old], 1: [new]})
    path = tmp_path / "catalog.csv"
    _, _, count = prepare_catalog(_settings(path), client=client, now=NOW)
    catalog = pd.read_csv(path)
    assert count == 1
    assert catalog["event_id"].tolist() == ["duplicate"]
    assert pd.to_datetime(catalog.loc[0, "updated_time_utc"], utc=True) == boundary + timedelta(
        hours=1
    )


def test_output_is_deterministically_chronological(monkeypatch, tmp_path):
    monkeypatch.setenv("ATHENA_BOOTSTRAP_LOOKBACK_DAYS", "365")
    earlier = NOW - timedelta(days=100)
    later = NOW - timedelta(days=10)
    client = RecordingClient({0: [_feature("later", later), _feature("earlier", earlier)]})
    path = tmp_path / "catalog.csv"
    prepare_catalog(_settings(path), client=client, now=NOW)
    catalog = pd.read_csv(path)
    assert catalog["event_id"].tolist() == ["earlier", "later"]
    assert {"event_time_utc", "updated_time_utc", "depth_km"} <= set(catalog.columns)


def test_middle_chunk_failure_preserves_existing_catalog(monkeypatch, tmp_path):
    monkeypatch.setenv("ATHENA_BOOTSTRAP_LOOKBACK_DAYS", "1095")
    path = tmp_path / "catalog.csv"
    path.write_text("existing production catalog", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"chunk .* to .*") as error:
        prepare_catalog(_settings(path), client=RecordingClient(fail_at=1), now=NOW)
    assert isinstance(error.value.__cause__, RuntimeError)
    assert path.read_text(encoding="utf-8") == "existing production catalog"
    assert not list(tmp_path.glob(".catalog.csv.*"))


def test_final_combined_empty_result_fails_safely(monkeypatch, tmp_path):
    monkeypatch.setenv("ATHENA_BOOTSTRAP_LOOKBACK_DAYS", "730")
    path = tmp_path / "catalog.csv"
    path.write_text("existing production catalog", encoding="utf-8")
    with pytest.raises(ValueError, match="empty catalog"):
        prepare_catalog(_settings(path), client=RecordingClient({0: [], 1: []}), now=NOW)
    assert path.read_text(encoding="utf-8") == "existing production catalog"
    assert not list(tmp_path.glob(".catalog.csv.*"))


def test_existing_one_year_override_still_works(monkeypatch, tmp_path):
    monkeypatch.setenv("ATHENA_BOOTSTRAP_LOOKBACK_DAYS", "365")
    client = RecordingClient()
    start, end, count = prepare_catalog(
        _settings(tmp_path / "catalog.csv"), client=client, now=NOW
    )
    assert (end - start).days == 365
    assert count == 1
    assert len(client.queries) == 1
