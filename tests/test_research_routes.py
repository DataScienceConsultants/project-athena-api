import csv
import json
from pathlib import Path

from app.main import app
from app.routers.research import get_research_artifact_service
from app.services.research_artifacts import ResearchArtifactService


def _write_bundle(root: Path) -> None:
    root.mkdir(parents=True)
    (root / "metadata.json").write_text(
        json.dumps(
            {
                "profile_id": "global-m6-1976-2025",
                "start_utc": "1976-01-01T00:00:00Z",
                "end_utc": "2026-01-01T00:00:00Z",
                "minimum_magnitude": 6.0,
                "catalog_event_count": 3,
                "fault_context_included": True,
                "catalog_source": "USGS ComCat",
            }
        ),
        encoding="utf-8",
    )
    fields = [
        "event_id",
        "time",
        "latitude",
        "longitude",
        "depth",
        "magnitude",
        "magnitude_type",
        "place",
        "status",
        "event_type",
        "source",
        "updated_at",
    ]
    with (root / "catalog.csv").open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            [
                {
                    "event_id": "west",
                    "time": "2000-01-01T00:00:00+00:00",
                    "latitude": "10",
                    "longitude": "179",
                    "depth": "12",
                    "magnitude": "6.5",
                    "magnitude_type": "mw",
                    "place": "West Dateline",
                    "status": "reviewed",
                    "event_type": "earthquake",
                    "source": "USGS",
                    "updated_at": "2000-01-02T00:00:00+00:00",
                },
                {
                    "event_id": "east",
                    "time": "2001-01-01T00:00:00+00:00",
                    "latitude": "11",
                    "longitude": "-179",
                    "depth": "18",
                    "magnitude": "7.1",
                    "magnitude_type": "mw",
                    "place": "East Dateline",
                    "status": "reviewed",
                    "event_type": "earthquake",
                    "source": "USGS",
                    "updated_at": "2001-01-02T00:00:00+00:00",
                },
                {
                    "event_id": "small",
                    "time": "2002-01-01T00:00:00+00:00",
                    "latitude": "0",
                    "longitude": "0",
                    "depth": "5",
                    "magnitude": "5.9",
                    "magnitude_type": "mw",
                    "place": "Below cohort filter",
                    "status": "reviewed",
                    "event_type": "earthquake",
                    "source": "USGS",
                    "updated_at": "2002-01-02T00:00:00+00:00",
                },
            ]
        )
    with (root / "fault_associations.csv").open(
        "w", encoding="utf-8", newline=""
    ) as target:
        writer = csv.DictWriter(
            target,
            fieldnames=("event_id", "fault_id", "fault_name", "distance_km", "fault_source"),
        )
        writer.writeheader()
        writer.writerow(
            {
                "event_id": "west",
                "fault_id": "fault-1",
                "fault_name": "Mapped fault",
                "distance_km": "24.5",
                "fault_source": "GEM Global Active Faults Database",
            }
        )


def _override_bundle(path: Path) -> None:
    app.dependency_overrides[get_research_artifact_service] = lambda: ResearchArtifactService(path)


def test_research_summary_reports_artifact_availability(client, tmp_path):
    bundle = tmp_path / "bundle"
    _write_bundle(bundle)
    _override_bundle(bundle)

    response = client.get("/research/global/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile_id"] == "global-m6-1976-2025"
    assert payload["availability"]["catalog"] is True
    assert payload["availability"]["fault_associations"] is True
    assert payload["availability"]["fault_geometry"] is False
    assert payload["report_is_nonpredictive"] is True


def test_earthquakes_support_dateline_bounds_and_magnitude_filter(client, tmp_path):
    bundle = tmp_path / "bundle"
    _write_bundle(bundle)
    _override_bundle(bundle)

    response = client.get(
        "/research/earthquakes",
        params={
            "minimum_magnitude": 6,
            "min_longitude": 170,
            "max_longitude": -170,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == ["west", "east"]
    assert payload["filtered_count"] == 2
    assert payload["items"][0]["coordinates"] == [179.0, 10.0]
    assert payload["items"][0]["athena_score"] is None


def test_missing_optional_fault_geometry_is_explicitly_unavailable(client, tmp_path):
    bundle = tmp_path / "bundle"
    _write_bundle(bundle)
    _override_bundle(bundle)

    response = client.get("/research/faults")

    assert response.status_code == 200
    assert response.json()["features"] == []
    assert response.json()["available"] is False


def test_connections_deliver_prepared_fault_associations(client, tmp_path):
    bundle = tmp_path / "bundle"
    _write_bundle(bundle)
    _override_bundle(bundle)

    response = client.get("/research/connections")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["items"][0]["event_id"] == "west"
    assert payload["items"][0]["fault_id"] == "fault-1"
    assert payload["items"][0]["distance_km"] == 24.5
    assert "not causal attribution" in payload["semantics"]


def test_missing_required_bundle_returns_503(client, tmp_path):
    _override_bundle(tmp_path / "missing")

    response = client.get("/research/global/summary")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "athena_research_bundle_unavailable"


def test_research_time_window_requires_timezone(client, tmp_path):
    bundle = tmp_path / "bundle"
    _write_bundle(bundle)
    _override_bundle(bundle)

    response = client.get("/research/earthquakes", params={"start": "2000-01-01T00:00:00"})

    assert response.status_code == 422
