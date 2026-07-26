import json

from app.main import app
from app.services.athena import AthenaReportUnavailableError, get_athena_service
from tests.conftest import REPORT


def test_observatory_serialization_is_unchanged(client):
    assert client.get("/observatory").json() == REPORT


def test_observatory_preserves_disclaimer(client):
    assert client.get("/observatory").json()["disclaimer"] == REPORT["disclaimer"]


def test_observatory_repeated_responses_are_deterministic(client):
    assert client.get("/observatory").content == client.get("/observatory").content


def test_observatory_is_strict_json(client):
    json.dumps(client.get("/observatory").json(), allow_nan=False)


def test_unavailable_catalog_returns_safe_503(client):
    class BrokenService:
        def build_report(self):
            raise AthenaReportUnavailableError("/secret/catalog.csv: sensitive detail")

    app.dependency_overrides[get_athena_service] = BrokenService
    response = client.get("/observatory")
    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "athena_report_unavailable",
            "message": "The Observatory intelligence report is currently unavailable.",
        }
    }
    assert b"secret" not in response.content
