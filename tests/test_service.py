import json
from importlib import import_module

from fastapi.middleware.cors import CORSMiddleware

from app.main import app, settings


def test_installed_athena_public_api_is_available():
    module = import_module("src.observatory")
    assert callable(module.build_observatory_intelligence_report)


def test_all_route_responses_are_strict_json(client):
    for path in (
        "/",
        "/health",
        "/version",
        "/status",
        "/summary",
        "/observatory",
        "/timeseries",
        "/timeseries/chart",
    ):
        json.dumps(client.get(path).json(), allow_nan=False)


def test_openapi_contains_all_required_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {
        "/health",
        "/version",
        "/status",
        "/summary",
        "/observatory",
        "/timeseries",
        "/timeseries/chart",
    } <= set(paths)


def test_openapi_states_nonpredictive_service(client):
    description = client.get("/openapi.json").json()["info"]["description"]
    assert "nonpredictive" in description


def test_application_uses_explicit_configured_cors_origins():
    cors_middleware = [
        middleware for middleware in app.user_middleware if middleware.cls is CORSMiddleware
    ]

    assert len(cors_middleware) == 1
    assert cors_middleware[0].kwargs["allow_origins"] == list(settings.allowed_origins)
    assert "*" not in cors_middleware[0].kwargs["allow_origins"]
