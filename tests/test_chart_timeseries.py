from copy import deepcopy
from datetime import date, timedelta

import pytest

from app.main import app
from app.services.athena import AthenaReportUnavailableError, get_athena_service
from tests.conftest import REPORT, FakeReport


def _chart_report(point_count: int = 35) -> dict:
    report = deepcopy(REPORT)
    start = date(2025, 1, 1)
    anomalies = []
    for index in range(point_count):
        current_date = start + timedelta(days=index)
        anomalies.append(
            {
                "current_start": f"{current_date.isoformat()}T00:00:00Z",
                "current_end": f"{(current_date + timedelta(days=1)).isoformat()}T00:00:00Z",
                "score": index + 0.25,
                "level": "typical" if index % 2 == 0 else "noteworthy",
                "available_metric_count": 4,
                "configured_metric_count": 4,
                "metric_scores": {
                    "event_count": {"current_value": index + 1.0, "historical_mean": 99.0},
                    "maximum_magnitude": {"current_value": index + 2.0, "raw_score": 88.0},
                    "total_energy_joules": {"current_value": index + 3.0, "weight": 0.4},
                    "mean_depth_km": {"current_value": index + 4.0, "explanation": "rich"},
                },
                "summary": "A daily textual summary that must not reach the chart response.",
            }
        )
    report["time_series"] = {
        "analysis_start": "2025-01-01T00:00:00Z",
        "analysis_end": "2025-12-31T00:00:00Z",
        "frequency": "daily",
        "source_event_count": 48_374,
        "candidate_period_count": point_count,
        "available_period_count": point_count,
        "unavailable_period_count": 0,
        "anomaly_results": anomalies,
        "points": [{"intentionally": "rich"}],
        "trend": {"direction": "stable"},
        "metadata": {"explanation": "not chart data"},
        "summary": "A historical summary.",
    }
    return report


@pytest.fixture
def chart_client(client, fake_service):
    fake_service.report = FakeReport(_chart_report())
    return client


def test_chart_endpoint_returns_compact_schema_and_exact_metric_values(chart_client):
    response = chart_client.get("/timeseries/chart?days=1")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "analysis_start",
        "analysis_end",
        "frequency",
        "source_event_count",
        "available_period_count",
        "points",
    }
    assert payload["points"] == [
        {
            "date": "2025-02-04",
            "anomaly_score": 34.25,
            "anomaly_level": "typical",
            "event_count": 35.0,
            "maximum_magnitude": 36.0,
            "total_energy_joules": 37.0,
            "mean_depth_km": 38.0,
        }
    ]


def test_chart_without_days_returns_complete_history_in_chronological_order(chart_client):
    payload = chart_client.get("/timeseries/chart").json()

    assert len(payload["points"]) == 35
    dates = [point["date"] for point in payload["points"]]
    assert dates == sorted(dates)
    assert dates[0] == "2025-01-01"
    assert dates[-1] == "2025-02-04"


@pytest.mark.parametrize(
    ("days", "expected_count", "first_date"),
    [(30, 30, "2025-01-06"), (3650, 35, "2025-01-01"), (1, 1, "2025-02-04")],
)
def test_chart_days_selects_most_recent_available_points(
    chart_client, days, expected_count, first_date
):
    points = chart_client.get(f"/timeseries/chart?days={days}").json()["points"]

    assert len(points) == expected_count
    assert points[0]["date"] == first_date


@pytest.mark.parametrize("days", [0, -1])
def test_chart_rejects_nonpositive_days_with_fastapi_validation(chart_client, days):
    assert chart_client.get(f"/timeseries/chart?days={days}").status_code == 422


def test_chart_missing_metric_is_null_not_zero(client, fake_service):
    report = _chart_report(1)
    del report["time_series"]["anomaly_results"][0]["metric_scores"]["mean_depth_km"]
    fake_service.report = FakeReport(report)

    point = client.get("/timeseries/chart").json()["points"][0]

    assert point["mean_depth_km"] is None
    assert point["event_count"] == 1.0


def test_chart_only_projects_existing_scientific_values(client, fake_service):
    report = _chart_report(1)
    anomaly = report["time_series"]["anomaly_results"][0]
    anomaly["score"] = None
    anomaly["level"] = "unavailable"
    anomaly["metric_scores"]["event_count"]["current_value"] = None
    fake_service.report = FakeReport(report)

    point = client.get("/timeseries/chart").json()["points"][0]

    assert point["anomaly_score"] is None
    assert point["anomaly_level"] == "unavailable"
    assert point["event_count"] is None


def test_chart_builds_the_unified_report_once(chart_client, fake_service):
    assert chart_client.get("/timeseries/chart").status_code == 200
    assert fake_service.calls == 1


def test_existing_timeseries_response_remains_unchanged(client, fake_service):
    report = _chart_report(2)
    fake_service.report = FakeReport(report)

    assert client.get("/timeseries").json() == report["time_series"]


def test_chart_returns_standard_safe_503_when_report_is_unavailable(client):
    class BrokenService:
        def build_report(self):
            raise AthenaReportUnavailableError("/secret/catalog.csv: sensitive detail")

    app.dependency_overrides[get_athena_service] = BrokenService
    response = client.get("/timeseries/chart")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "athena_report_unavailable",
            "message": "The Observatory intelligence report is currently unavailable.",
        }
    }
    assert b"secret" not in response.content
