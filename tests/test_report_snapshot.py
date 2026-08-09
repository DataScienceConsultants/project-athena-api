import json
import os
from datetime import UTC, datetime

import pandas as pd
import pytest

from app.build_report_snapshot import build_report_snapshot
from app.config import Settings
from app.services.athena import AthenaReportUnavailableError, AthenaService
from tests.conftest import FakeReport

CATALOG_TIME = datetime.now(UTC).replace(microsecond=0)


def _settings(tmp_path, *, region="puerto_rico"):
    catalog = tmp_path / "catalog.csv"
    snapshot = tmp_path / "report.json"
    pd.DataFrame(
        {
            "event_time_utc": [CATALOG_TIME.isoformat(), CATALOG_TIME.isoformat()],
            "event_id": ["one", "two"],
        }
    ).to_csv(catalog, index=False)
    return Settings(
        default_catalog_path=str(catalog),
        report_snapshot_path=str(snapshot),
        default_region_key=region,
    )


def test_snapshot_build_is_strict_atomic_and_contains_metadata(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    destination = tmp_path / "nested" / "report.json"
    calls = []

    def builder(**kwargs):
        calls.append(kwargs)
        return FakeReport()

    replace_calls = []
    real_replace = os.replace

    def recording_replace(source, target):
        replace_calls.append((source, target))
        real_replace(source, target)

    monkeypatch.setattr("app.build_report_snapshot.os.replace", recording_replace)
    payload = build_report_snapshot(settings, destination=destination, builder=builder)

    assert calls == [
        {"region_key": "puerto_rico", "catalog_path": settings.default_catalog_path}
    ]
    assert payload["metadata"]["source_event_count"] == 2
    assert payload["metadata"]["region_key"] == "puerto_rico"
    assert payload["metadata"]["catalog_as_of_utc"].endswith("Z")
    assert json.loads(destination.read_text(encoding="utf-8"))["report"] == FakeReport().to_dict()
    assert len(replace_calls) == 1
    assert replace_calls[0][1] == destination


def test_snapshot_strict_json_failure_preserves_existing_file(tmp_path):
    settings = _settings(tmp_path)
    destination = tmp_path / "report.json"
    destination.write_text('{"old":true}', encoding="utf-8")
    bad_report = FakeReport({"not_finite": float("nan")})

    with pytest.raises(ValueError):
        build_report_snapshot(
            settings, destination=destination, builder=lambda **kwargs: bad_report
        )

    assert destination.read_text(encoding="utf-8") == '{"old":true}'
    assert not list(tmp_path.glob(".report.json.*"))


def test_builder_failure_preserves_existing_snapshot(tmp_path):
    settings = _settings(tmp_path)
    destination = tmp_path / "report.json"
    destination.write_text("existing", encoding="utf-8")

    def fail(**kwargs):
        raise RuntimeError("science failed")

    with pytest.raises(RuntimeError, match="science failed"):
        build_report_snapshot(settings, destination=destination, builder=fail)
    assert destination.read_text(encoding="utf-8") == "existing"


def test_service_loads_valid_snapshot_without_calling_builder(tmp_path):
    settings = _settings(tmp_path)
    build_report_snapshot(settings, builder=lambda **kwargs: FakeReport())

    def forbidden(**kwargs):
        raise AssertionError("scientific builder was invoked")

    service = AthenaService(settings=settings, builder=forbidden)
    assert service.build_report().to_dict() == FakeReport().to_dict()
    assert service.build_report().to_dict() == FakeReport().to_dict()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(report=[]),
        lambda payload: payload["metadata"].update(source_event_count=99),
        lambda payload: payload["metadata"].update(catalog_as_of_utc="2020-01-01T00:00:00Z"),
        lambda payload: payload["metadata"].update(region_key="wrong"),
    ],
)
def test_service_rejects_incompatible_snapshot(tmp_path, mutation):
    settings = _settings(tmp_path)
    payload = build_report_snapshot(settings, builder=lambda **kwargs: FakeReport())
    mutation(payload)
    settings_snapshot = settings.report_snapshot_path
    with open(settings_snapshot, "w", encoding="utf-8") as snapshot:
        json.dump(payload, snapshot)
    with pytest.raises(AthenaReportUnavailableError):
        AthenaService(settings=settings).build_report()


@pytest.mark.parametrize("content", [None, "not json", "[]", "{}"])
def test_service_rejects_missing_malformed_or_wrong_snapshot(tmp_path, content):
    settings = _settings(tmp_path)
    if content is not None:
        with open(settings.report_snapshot_path, "w", encoding="utf-8") as snapshot:
            snapshot.write(content)
    with pytest.raises(AthenaReportUnavailableError):
        AthenaService(settings=settings).build_report()


def test_service_rejects_snapshot_older_than_catalog(tmp_path):
    settings = _settings(tmp_path)
    build_report_snapshot(settings, builder=lambda **kwargs: FakeReport())
    snapshot_stat = os.stat(settings.report_snapshot_path)
    os.utime(
        settings.default_catalog_path,
        ns=(snapshot_stat.st_atime_ns, snapshot_stat.st_mtime_ns + 1_000_000),
    )
    with pytest.raises(AthenaReportUnavailableError):
        AthenaService(settings=settings).build_report()
