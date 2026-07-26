from copy import deepcopy

from tests.conftest import REPORT, FakeReport


def test_status_with_available_anomaly(client):
    payload = client.get("/status").json()
    assert payload["latest_anomaly_score"] == 1.25
    assert payload["latest_anomaly_level"] == "typical"


def test_status_with_unavailable_anomaly(client, fake_service):
    data = deepcopy(REPORT)
    data["latest_anomaly"] = None
    fake_service.report = FakeReport(data)
    payload = client.get("/status").json()
    assert payload["latest_anomaly_score"] is None
    assert payload["latest_anomaly_level"] is None


def test_status_preserves_canonical_z_timestamp(client):
    assert client.get("/status").json()["catalog_as_of_utc"] == "2026-01-02T03:04:05Z"


def test_status_is_explicitly_nonpredictive(client):
    assert client.get("/status").json()["report_is_nonpredictive"] is True


def test_status_builds_report_once(client, fake_service):
    client.get("/status")
    assert fake_service.calls == 1
