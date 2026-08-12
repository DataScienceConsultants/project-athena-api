def test_dashboard_is_served(client):
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Athena Research Dashboard" in response.text
    assert "Research use only" in response.text
    assert "/dashboard/assets/styles.css" in response.text
    assert "/dashboard/assets/app.js" in response.text


def test_dashboard_assets_are_served(client):
    stylesheet = client.get("/dashboard/assets/styles.css")
    script = client.get("/dashboard/assets/app.js")

    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert ".dashboard-grid" in stylesheet.text

    assert script.status_code == 200
    assert script.headers["content-type"].startswith("text/javascript")
    assert 'fetchJSON("/summary")' in script.text
    assert '"/timeseries/chart"' in script.text


def test_discovery_includes_dashboard(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["endpoints"]["dashboard"] == "/dashboard"
