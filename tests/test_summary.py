from copy import deepcopy

from app.main import app
from app.services.athena import AthenaReportUnavailableError, get_athena_service
from tests.conftest import REPORT, FakeReport


def test_summary_projects_complete_serialized_report(client):
    response = client.get("/summary")
    assert response.status_code == 200
    assert response.json() == {
        "region_key": "test-region",
        "region_name": "Test Region",
        "overall_status": "historical_observations_available",
        "catalog_as_of_utc": "2026-01-02T03:04:05Z",
        "source_event_count": 12,
        "latest_anomaly_score": 1.25,
        "latest_anomaly_level": "typical",
        "trend_direction": "stable",
        "trend_strength": "weak",
        "swarm_count": 2,
        "executive_summary": "Historical activity remains stable.",
        "disclaimer": "Historical observations only; nonpredictive.",
        "report_is_nonpredictive": True,
    }


def test_summary_accepts_missing_optional_anomaly_and_swarm(client, fake_service):
    data = deepcopy(REPORT)
    data["latest_anomaly"] = None
    data["swarm"] = None
    fake_service.report = FakeReport(data)

    payload = client.get("/summary").json()

    assert payload["latest_anomaly_score"] is None
    assert payload["latest_anomaly_level"] is None
    assert payload["swarm_count"] is None


def test_summary_returns_safe_503_when_report_is_unavailable(client):
    class BrokenService:
        def build_report(self):
            raise AthenaReportUnavailableError("/secret/catalog.csv: sensitive detail")

    app.dependency_overrides[get_athena_service] = BrokenService
    response = client.get("/summary")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "athena_report_unavailable",
            "message": "The Observatory intelligence report is currently unavailable.",
        }
    }
    assert b"secret" not in response.content


def test_summary_builds_unified_report_once(client, fake_service):
    assert client.get("/summary").status_code == 200
    assert fake_service.calls == 1
