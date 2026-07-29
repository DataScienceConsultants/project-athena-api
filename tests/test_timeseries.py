import json

from tests.conftest import REPORT


def test_timeseries_returns_only_time_series(client):
    assert client.get("/timeseries").json() == REPORT["time_series"]


def test_timeseries_has_exact_top_level_fields(client):
    assert set(client.get("/timeseries").json()) == {"frequency", "points", "trend", "metadata"}


def test_timeseries_preserves_point_timestamp(client):
    point = client.get("/timeseries").json()["points"][0]
    assert point["timestamp"].endswith("Z")


def test_timeseries_builds_unified_report_once(client, fake_service):
    client.get("/timeseries")
    assert fake_service.calls == 1


def test_timeseries_is_strict_json(client):
    json.dumps(client.get("/timeseries").json(), allow_nan=False)
