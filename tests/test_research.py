import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

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
    assert metadata["athena_mode"] == "research"
    assert metadata["report_is_nonpredictive"] is True
    assert json.loads((output / "metadata.json").read_text()) == metadata
    assert json.loads((output / "timeseries.json").read_text())["frequency"] == "daily"
    assert (
        json.loads((output / "observatory_report.json").read_text())["region"]["region_key"]
        == "venezuela"
    )


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
