import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.bootstrap_catalog import configured_region
from app.config import Settings
from app.research import build_parser, default_output_path, parse_date, run_research

START = datetime(2018, 1, 1, tzinfo=UTC)
END = datetime(2018, 1, 3, tzinfo=UTC)


def _feature(query):
    event_time = query.start_time + timedelta(hours=1)
    return {
        "id": "research-event",
        "properties": {
            "time": int(event_time.timestamp() * 1000),
            "updated": int(event_time.timestamp() * 1000),
            "mag": 3.1,
            "magType": "mb",
            "place": "Research region",
            "type": "earthquake",
        },
        "geometry": {"coordinates": [-62.0, 10.5, 12.0]},
    }


class Client:
    def __init__(self):
        self.queries = []

    def fetch(self, query):
        self.queries.append(query)
        return [_feature(query)]


class Report:
    def to_dict(self):
        return {
            "region": {"region_key": "venezuela"},
            "disclaimer": "Historical descriptive analysis; nonpredictive.",
            "time_series": {
                "analysis_start": "2018-01-01T00:00:00Z",
                "analysis_end": "2018-01-03T00:00:00Z",
                "frequency": "daily",
                "source_event_count": 1,
                "candidate_period_count": 2,
                "available_period_count": 1,
                "unavailable_period_count": 1,
                "anomaly_results": [{"current_start": "2018-01-01T00:00:00Z"}],
            },
        }


def builder(**kwargs):
    assert kwargs["region_key"] == "venezuela"
    return Report()


def test_region_lookup_and_invalid_region(tmp_path):
    metadata = run_research(
        region_key="venezuela",
        start=START,
        end=END,
        output_dir=tmp_path / "valid",
        client=Client(),
        report_builder=builder,
    )
    assert metadata["region_name"] == "Venezuela and northeastern Caribbean seismic region"
    with pytest.raises(ValueError, match="not found"):
        run_research(region_key="missing", start=START, end=END, output_dir=tmp_path / "bad")


def test_date_parsing_and_invalid_range(tmp_path):
    assert parse_date("2020-02-29") == datetime(2020, 2, 29, tzinfo=UTC)
    with pytest.raises(Exception, match="YYYY-MM-DD"):
        parse_date("02/29/2020")
    with pytest.raises(ValueError, match="earlier"):
        run_research(region_key="venezuela", start=END, end=END, output_dir=tmp_path)


def test_cli_defaults_and_overrides():
    parser = build_parser()
    defaults = parser.parse_args(
        ["--region", "venezuela", "--start", "2018-01-01", "--end", "2018-01-02"]
    )
    assert defaults.output is None
    assert defaults.chunk_days == 365
    assert default_output_path("venezuela") == Path("data/research/venezuela")
    custom = parser.parse_args(
        [
            "--region",
            "venezuela",
            "--start",
            "2018-01-01",
            "--end",
            "2018-01-02",
            "--output",
            "bench",
            "--minimum-magnitude",
            "2.5",
            "--chunk-days",
            "30",
        ]
    )
    assert custom.output == Path("bench")
    assert custom.minimum_magnitude == 2.5
    assert custom.chunk_days == 30


def test_colombia_resolves_and_cli_uses_isolated_default_path():
    region = configured_region("colombia")
    assert region == {
        "name": "Colombia and adjacent seismic region",
        "description": (
            "Seismic-study bounds covering Colombia, its Pacific subduction margin, and adjacent "
            "Caribbean and Andean seismic settings around the 10 August 2026 earthquake; they are "
            "not political boundaries."
        ),
        "bounds": {
            "min_latitude": -5.0,
            "max_latitude": 14.0,
            "min_longitude": -82.0,
            "max_longitude": -66.0,
        },
        "default_minimum_magnitude": 2.5,
    }
    args = build_parser().parse_args(
        ["--region", "colombia", "--start", "2021-01-01", "--end", "2026-08-11"]
    )
    assert args.region == "colombia"
    assert default_output_path(args.region) == Path("data/research/colombia")


def test_complete_artifacts_metadata_and_production_isolation(tmp_path):
    production_catalog = tmp_path / "production.csv"
    production_report = tmp_path / "production.json"
    production_catalog.write_text("production catalog", encoding="utf-8")
    production_report.write_text("production report", encoding="utf-8")
    output = tmp_path / "research"
    client = Client()
    metadata = run_research(
        region_key="venezuela",
        start=START,
        end=END,
        output_dir=output,
        minimum_magnitude=2.5,
        chunk_days=1,
        client=client,
        report_builder=builder,
        generated_at=datetime(2020, 1, 1, tzinfo=UTC),
        settings=Settings(
            default_catalog_path=str(production_catalog),
            report_snapshot_path=str(production_report),
        ),
    )
    assert {path.name for path in output.iterdir()} == {
        "catalog.csv",
        "observatory_report.json",
        "timeseries.json",
        "metadata.json",
    }
    assert production_catalog.read_text(encoding="utf-8") == "production catalog"
    assert production_report.read_text(encoding="utf-8") == "production report"
    assert len(client.queries) == 2
    assert all(query.minimum_magnitude == 2.5 for query in client.queries)
    assert metadata["event_count"] == 1
    assert metadata["timeseries_period_count"] == 1
    assert metadata["timeseries_available_period_count"] == 1
    assert metadata["timeseries_unavailable_period_count"] == 1
    assert metadata["athena_mode"] == "research"
    assert metadata["report_is_nonpredictive"] is True
    assert json.loads((output / "metadata.json").read_text()) == metadata
    assert json.loads((output / "timeseries.json").read_text())["frequency"] == "daily"
    assert (
        json.loads((output / "observatory_report.json").read_text())["region"]["region_key"]
        == "venezuela"
    )


def test_real_builder_uses_repository_region_when_packaged_config_lacks_it(tmp_path):
    """Regression: catalog, report, and series share the research runner's region."""
    from src.observatory.builder import resolve_region

    packaged_config = tmp_path / "packaged" / "config" / "regions.json"
    packaged_config.parent.mkdir(parents=True)
    packaged_config.write_text(
        json.dumps(
            {
                "default_region": "puerto_rico",
                "regions": {"puerto_rico": {"name": "Puerto Rico"}},
            }
        )
    )
    with pytest.raises(ValueError, match='Region "venezuela" was not found'):
        resolve_region(
            catalog_path="catalog.csv",
            region_key="venezuela",
            configuration_path=packaged_config,
        )

    output = tmp_path / "data" / "research" / "venezuela"
    metadata = run_research(
        region_key="venezuela",
        start=START,
        end=END,
        output_dir=output,
        client=Client(),
    )

    report = json.loads((output / "observatory_report.json").read_text())
    timeseries = json.loads((output / "timeseries.json").read_text())
    assert report["observatory"]["catalog"]["region_key"] == "venezuela"
    assert report["observatory"]["catalog"]["region_name"] == metadata["region_name"]
    assert timeseries == report["time_series"]
    assert metadata["region_key"] == "venezuela"
    assert output.relative_to(tmp_path) == Path("data/research/venezuela")


def test_colombia_uses_existing_report_and_timeseries_pipeline_with_production_isolation(tmp_path):
    production_catalog = tmp_path / "data" / "catalog.csv"
    production_report = tmp_path / "data" / "observatory_report.json"
    production_catalog.parent.mkdir()
    production_catalog.write_text("production catalog", encoding="utf-8")
    production_report.write_text("production report", encoding="utf-8")

    class ColombiaReport(Report):
        def to_dict(self):
            payload = super().to_dict()
            payload["region"] = {"region_key": "colombia"}
            return payload

    def colombia_builder(**kwargs):
        assert kwargs["region_key"] == "colombia"
        return ColombiaReport()

    class ColombiaClient:
        def fetch(self, query):
            event_time = query.start_time + timedelta(hours=1)
            return [
                {
                    "id": "colombia-research-event",
                    "properties": {
                        "time": int(event_time.timestamp() * 1000),
                        "updated": int(event_time.timestamp() * 1000),
                        "mag": 3.1,
                        "magType": "mb",
                        "place": "Colombia research region",
                        "type": "earthquake",
                    },
                    "geometry": {"coordinates": [-74.0, 5.0, 12.0]},
                }
            ]

    output = tmp_path / default_output_path("colombia")
    metadata = run_research(
        region_key="colombia",
        start=START,
        end=END,
        output_dir=output,
        client=ColombiaClient(),
        report_builder=colombia_builder,
        settings=Settings(
            default_catalog_path=str(production_catalog),
            report_snapshot_path=str(production_report),
        ),
    )

    report = json.loads((output / "observatory_report.json").read_text())
    timeseries = json.loads((output / "timeseries.json").read_text())
    assert metadata["region_key"] == "colombia"
    assert metadata["region_name"] == "Colombia and adjacent seismic region"
    assert metadata["minimum_magnitude"] == 2.5
    assert report["region"]["region_key"] == "colombia"
    assert timeseries == report["time_series"]
    assert output.relative_to(tmp_path) == Path("data/research/colombia")
    assert production_catalog.read_text(encoding="utf-8") == "production catalog"
    assert production_report.read_text(encoding="utf-8") == "production report"


def test_builder_failure_never_promotes_partial_output(tmp_path):
    output = tmp_path / "research"
    output.mkdir()
    (output / "sentinel").write_text("old complete output", encoding="utf-8")

    def fail(**kwargs):
        raise RuntimeError("report failed")

    with pytest.raises(RuntimeError, match="report failed"):
        run_research(
            region_key="venezuela",
            start=START,
            end=END,
            output_dir=output,
            client=Client(),
            report_builder=fail,
        )
    assert [path.name for path in output.iterdir()] == ["sentinel"]
    assert not list(tmp_path.glob(".research.candidate.*"))
