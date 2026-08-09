import platform


def test_version_payload(client):
    payload = client.get("/version").json()
    assert payload["api_version"] == "0.1.0"
    assert payload["python_version"] == platform.python_version()
    assert len(payload["athena_version"]) == 40


def test_version_is_successful(client):
    assert client.get("/version").status_code == 200


def test_root_discovers_required_routes(client):
    endpoints = client.get("/").json()["endpoints"]
    expected_endpoints = {
        "/health",
        "/version",
        "/status",
        "/summary",
        "/observatory",
        "/timeseries",
        "/timeseries/chart",
    }
    assert set(endpoints.values()) == expected_endpoints
