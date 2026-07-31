from fastapi.testclient import TestClient

from app.main import app


def test_default_local_origin_is_allowed():
    response = TestClient(app).get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unlisted_origin_is_not_allowed():
    response = TestClient(app).get("/health", headers={"Origin": "https://untrusted.test"})
    assert "access-control-allow-origin" not in response.headers
