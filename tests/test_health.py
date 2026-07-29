from app.main import app
from app.services.athena import get_athena_service


def test_health_payload(client):
    assert client.get("/health").json() == {
        "status": "healthy",
        "service": "project-athena-api",
        "version": "0.1.0",
    }


def test_health_is_successful(client):
    assert client.get("/health").status_code == 200


def test_health_does_not_resolve_athena_dependency(client):
    app.dependency_overrides[get_athena_service] = lambda: (_ for _ in ()).throw(AssertionError())
    assert client.get("/health").status_code == 200


def test_health_is_json(client):
    assert client.get("/health").headers["content-type"].startswith("application/json")
