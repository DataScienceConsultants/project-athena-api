import csv
import json
from datetime import date, timedelta

import pytest

from app.benchmark import (
    analyze,
    base_rates,
    catalog_adequacy,
    classify_regime,
    cluster_count,
    days_since_last,
    future_event_associations,
    longest_run,
    main,
    window_metrics,
    window_points,
)


def point(day, score, event_count=1, magnitude=2.0):
    return {
        "current_start": f"{day.isoformat()}T00:00:00Z",
        "score": score,
        "level": "noteworthy" if score is not None and score >= 70 else "typical",
        "metric_scores": {
            "event_count": {"current_value": event_count},
            "maximum_magnitude": {"current_value": magnitude},
            "total_energy_joules": {"current_value": None},
            "mean_depth_km": {"current_value": 10.0},
        },
    }


EVENT = date(2026, 8, 10)


def test_windows_have_exact_boundaries_and_exclude_event_day():
    points = [point(EVENT - timedelta(days=n), n) for n in range(0, 32)]
    for days in (7, 14, 30):
        selected = window_points(points, EVENT, days)
        assert len(selected) == days
        assert min(item["current_start"][:10] for item in selected) == str(
            EVENT - timedelta(days=days)
        )
        assert all(item["current_start"][:10] != str(EVENT) for item in selected)


def test_thresholds_runs_clusters_recency_and_nulls():
    points = [
        point(EVENT - timedelta(days=6), 70),
        point(EVENT - timedelta(days=5), 80),
        point(EVENT - timedelta(days=4), None, event_count=None),
        point(EVENT - timedelta(days=3), 80),
        point(EVENT - timedelta(days=2), 80),
    ]
    metrics = window_metrics(points)
    assert metrics["days_ge70"] == 4
    assert metrics["days_ge80"] == 3
    assert metrics["scored_day_count"] == 4
    assert metrics["mean_total_energy_joules"] is None
    assert longest_run(points, 80) == 2
    assert cluster_count(points, 70) == 2
    assert days_since_last(points, EVENT, 80) == 2
    assert days_since_last(points, EVENT, 90) is None


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        ([], "quiet"),
        ([70], "isolated_anomaly"),
        ([70, 10, 70], "intermittent_anomalies"),
        ([70, 80, 70], "persistent_anomalous_regime"),
    ],
)
def test_regime_classification(scores, expected):
    points = [
        point(EVENT - timedelta(days=len(scores) - index), score)
        for index, score in enumerate(scores)
    ]
    assert classify_regime(points) == expected


def test_event_day_base_rate_and_catalog_adequacy():
    points = [point(EVENT - timedelta(days=1), 70), point(EVENT, 100, magnitude=7.4)]
    series = {
        "source_event_count": 2,
        "candidate_period_count": 2,
        "available_period_count": 2,
        "unavailable_period_count": 0,
        "anomaly_results": points,
    }
    result = analyze(
        {
            "benchmark_id": "x",
            "region_key": "colombia",
            "event_date_utc": str(EVENT),
            "event_magnitude": 7.4,
        },
        series,
    )
    assert result["event_day_metrics"]["event_day_anomaly_score"] == 100
    assert result["pre_event_windows"]["7_day"]["maximum_anomaly_score"] == 70
    assert base_rates(points)["percentage_ge70"] == 100
    assert catalog_adequacy(series, points)["status"] == "usable"
    series["available_period_count"] = 1
    assert catalog_adequacy(series, points)["status"] == "limited"
    series["available_period_count"] = 0
    assert catalog_adequacy(series, points)["status"] == "insufficient"


def test_fixed_future_associations_are_independent_and_exclude_same_day():
    anomaly_day = EVENT - timedelta(days=10)
    points = [
        # This same-day M7 must not count because association horizons start at +1 day.
        point(anomaly_day, 80, magnitude=7.2),
        point(anomaly_day + timedelta(days=1), 10, magnitude=5.5),
        point(anomaly_day + timedelta(days=3), 10, magnitude=6.5),
        point(anomaly_day + timedelta(days=7), 10, magnitude=7.1),
        # A second qualifying day has no future event, making the denominator visibly two.
        point(EVENT, 80, magnitude=4.0),
    ]

    associations = future_event_associations(points)
    m5 = associations["magnitude_ge5"]["threshold_80"]
    m6 = associations["magnitude_ge6"]["threshold_80"]
    m7 = associations["magnitude_ge7"]["threshold_80"]
    assert m5["followed_by_event_within_1d_count"] == 1
    assert m6["followed_by_event_within_1d_count"] == 0
    assert m6["followed_by_event_within_3d_count"] == 1
    assert m7["followed_by_event_within_3d_count"] == 0
    assert m7["followed_by_event_within_7d_count"] == 1
    assert m7["followed_by_event_within_7d_fraction"] == 0.5
    assert m7["qualifying_anomaly_day_count"] == 2


def test_fixed_associations_do_not_depend_on_benchmark_magnitude():
    anomaly_day = EVENT - timedelta(days=2)
    points = [point(anomaly_day, 75), point(anomaly_day + timedelta(days=1), 10, magnitude=6.8)]
    series = {
        "candidate_period_count": 2,
        "available_period_count": 2,
        "anomaly_results": points,
    }

    low = analyze(
        {"benchmark_id": "low", "event_date_utc": str(EVENT), "event_magnitude": 6.0},
        series,
    )
    high = analyze(
        {"benchmark_id": "high", "event_date_utc": str(EVENT), "event_magnitude": 7.0},
        series,
    )
    assert low["future_event_associations"] == high["future_event_associations"]
    assert low["benchmark_magnitude_associations"] != high["benchmark_magnitude_associations"]
    assert low["benchmark_magnitude_associations"]["required_magnitude"] == 6.0
    assert high["benchmark_magnitude_associations"]["required_magnitude"] == 7.0


def test_all_writes_json_csv_and_does_not_touch_production(tmp_path, monkeypatch):
    benchmark = {
        "benchmark_id": "synthetic",
        "name": "Synthetic observed event",
        "region_key": "test",
        "event_date_utc": str(EVENT),
        "event_magnitude": 7.0,
        "analysis_start": "2026-01-01",
        "analysis_end": "2026-08-11",
        "notes": "test",
    }
    config = tmp_path / "benchmarks.json"
    config.write_text(json.dumps({"benchmarks": [benchmark]}))
    research = tmp_path / "research" / "test"
    research.mkdir(parents=True)
    series = {
        "source_event_count": 1,
        "candidate_period_count": 1,
        "available_period_count": 1,
        "unavailable_period_count": 0,
        "anomaly_results": [point(EVENT, 50, magnitude=7.0)],
    }
    (research / "timeseries.json").write_text(json.dumps(series))
    production = tmp_path / "catalog.csv"
    production.write_text("unchanged")
    output = tmp_path / "output"
    monkeypatch.setattr("app.benchmark.CONFIG_PATH", config)
    monkeypatch.setattr("app.benchmark.RESEARCH_ROOT", tmp_path / "research")
    main(["--all", "--output", str(output)])
    assert json.loads((output / "synthetic" / "result.json").read_text())["research_only"] is True
    assert len(json.loads((output / "summary.json").read_text())) == 1
    with (output / "summary.csv").open() as stream:
        assert list(csv.DictReader(stream))[0]["benchmark_id"] == "synthetic"
    assert production.read_text() == "unchanged"
