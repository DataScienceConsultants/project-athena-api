from copy import deepcopy
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.athena import get_athena_service

REPORT = {
    "region": {"key": "test-region", "name": "Test Region"},
    "overall_status": "historical_observations_available",
    "catalog": {"as_of_utc": "2026-01-02T03:04:05Z", "source_event_count": 12},
    "latest_anomaly": {"score": 1.25, "level": "typical"},
    "swarm": {"count": 2},
    "time_series": {
        "analysis_start": "2026-01-02T00:00:00Z",
        "analysis_end": "2026-01-03T00:00:00Z",
        "frequency": "daily",
        "source_event_count": 12,
        "available_period_count": 1,
        "anomaly_results": [
            {
                "current_start": "2026-01-02T00:00:00Z",
                "score": 1.25,
                "level": "typical",
                "metric_scores": {},
            }
        ],
        "points": [{"timestamp": "2026-01-02T00:00:00Z", "event_count": 2}],
        "trend": {"direction": "stable", "strength": "weak"},
        "metadata": {"source": "fixture"},
    },
    "report_is_nonpredictive": True,
    "executive_summary": "Historical activity remains stable.",
    "disclaimer": "Historical observations only; nonpredictive.",
}


class FakeReport:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data = deepcopy(data or REPORT)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self.data)


class FakeService:
    def __init__(self, report: FakeReport | None = None) -> None:
        self.report = report or FakeReport()
        self.calls = 0

    def build_report(self) -> FakeReport:
        self.calls += 1
        return self.report


@pytest.fixture
def fake_service() -> FakeService:
    return FakeService()


@pytest.fixture
def client(fake_service: FakeService):
    app.dependency_overrides[get_athena_service] = lambda: fake_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
