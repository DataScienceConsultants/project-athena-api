import json
from importlib import import_module

import pytest
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.main import app, settings
from app.services.athena import AthenaReportUnavailableError, AthenaService
from tests.conftest import FakeReport


def test_service_invokes_unified_builder_once(monkeypatch):
    calls = []

    def builder(**kwargs):
        calls.append(kwargs)
        return FakeReport()

    monkeypatch.setattr("app.services.athena.validate_catalog_readiness", lambda settings: None)
    service = AthenaService(builder=builder, settings=Settings())
    assert service.build_report().to_dict()
    assert calls == [{"region_key": "puerto_rico", "catalog_path": "data/catalog.csv"}]


def test_installed_athena_public_api_is_available():
    module = import_module("src.observatory")
    assert callable(module.build_observatory_intelligence_report)


@pytest.mark.parametrize("exception", [FileNotFoundError("missing"), ValueError("bad report")])
def test_service_translates_expected_failures(exception, monkeypatch):
    def builder(**kwargs):
        raise exception

    monkeypatch.setattr("app.services.athena.validate_catalog_readiness", lambda settings: None)
    with pytest.raises(AthenaReportUnavailableError):
        AthenaService(builder=builder).build_report()


def test_service_does_not_swallow_unexpected_programming_error(monkeypatch):
    def builder(**kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr("app.services.athena.validate_catalog_readiness", lambda settings: None)
    with pytest.raises(RuntimeError, match="bug"):
        AthenaService(builder=builder).build_report()


def test_all_route_responses_are_strict_json(client):
    for path in (
        "/",
        "/health",
        "/version",
        "/status",
        "/summary",
        "/observatory",
        "/timeseries",
    ):
        json.dumps(client.get(path).json(), allow_nan=False)


def test_openapi_contains_all_required_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/health", "/version", "/status", "/summary", "/observatory", "/timeseries"} <= set(
        paths
    )


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
