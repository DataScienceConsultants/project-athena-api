"""Research-only historical measurements of frozen Athena time-series artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("config/benchmarks.json")
RESEARCH_ROOT = Path("data/research")
DEFAULT_OUTPUT = Path("data/benchmarks")
THRESHOLDS = (70, 75, 80, 90, 95)
HORIZONS = (1, 3, 7, 10, 14, 30)
ASSOCIATION_MAGNITUDES = (5, 6, 7)
CONTROL_EXCLUSION_DAYS = 30
REGIMES = (
    "quiet",
    "isolated_anomaly",
    "intermittent_anomalies",
    "persistent_anomalous_regime",
)


def _day(point: dict[str, Any]) -> date:
    return date.fromisoformat(point["current_start"][:10])


def _metric(point: dict[str, Any], name: str) -> Any:
    value = point.get("metric_scores", {}).get(name)
    return value.get("current_value") if isinstance(value, dict) else None


def _numbers(values: Iterable[Any]) -> list[float]:
    return [
        float(value) for value in values if isinstance(value, int | float) and not math.isnan(value)
    ]


def _mean(values: Iterable[Any]) -> float | None:
    valid = _numbers(values)
    return statistics.fmean(valid) if valid else None


def _maximum(values: Iterable[Any]) -> float | None:
    valid = _numbers(values)
    return max(valid) if valid else None


def window_points(
    points: Sequence[dict[str, Any]], event_day: date, days: int
) -> list[dict[str, Any]]:
    """Select [event day - days, event day), explicitly excluding the event day."""
    start = event_day - timedelta(days=days)
    return [point for point in points if start <= _day(point) < event_day]


def window_metrics(points: Sequence[dict[str, Any]]) -> dict[str, Any]:
    scores = _numbers(point.get("score") for point in points)
    result: dict[str, Any] = {
        "scored_day_count": len(scores),
        "mean_anomaly_score": statistics.fmean(scores) if scores else None,
        "median_anomaly_score": statistics.median(scores) if scores else None,
        "maximum_anomaly_score": max(scores) if scores else None,
        "minimum_anomaly_score": min(scores) if scores else None,
        "standard_deviation_anomaly_score": statistics.pstdev(scores) if scores else None,
    }
    for threshold in THRESHOLDS:
        result[f"days_ge{threshold}"] = sum(score >= threshold for score in scores)
    result["days_eq100"] = sum(score == 100 for score in scores)
    for name in ("event_count", "maximum_magnitude", "total_energy_joules", "mean_depth_km"):
        values = [_metric(point, name) for point in points]
        result[f"mean_{name}"] = _mean(values)
        if name != "mean_depth_km":
            result[f"maximum_{name}"] = _maximum(values)
    result["maximum_pre_event_magnitude"] = result.pop("maximum_maximum_magnitude")
    return result


def longest_run(points: Sequence[dict[str, Any]], threshold: int) -> int:
    longest = current = 0
    previous: date | None = None
    for point in sorted(points, key=_day):
        score = point.get("score")
        day = _day(point)
        if isinstance(score, int | float) and score >= threshold:
            current = current + 1 if previous == day - timedelta(days=1) else 1
            longest = max(longest, current)
            previous = day
        else:
            current = 0
            previous = None
    return longest


def cluster_count(points: Sequence[dict[str, Any]], threshold: int) -> int:
    count = 0
    active = False
    previous: date | None = None
    for point in sorted(points, key=_day):
        day = _day(point)
        qualifies = isinstance(point.get("score"), int | float) and point["score"] >= threshold
        if qualifies and (not active or previous != day - timedelta(days=1)):
            count += 1
        active = qualifies
        previous = day
    return count


def persistence_metrics(points30: Sequence[dict[str, Any]], event_day: date) -> dict[str, Any]:
    result = {f"longest_consecutive_run_ge{t}": longest_run(points30, t) for t in (70, 75, 80)}
    result["distinct_ge70_clusters"] = cluster_count(points30, 70)
    for threshold in (70, 80):
        for days in (7, 14, 30):
            recent = window_points(points30, event_day, days)
            result[f"count_ge{threshold}_most_recent_{days}d"] = sum(
                isinstance(point.get("score"), int | float) and point["score"] >= threshold
                for point in recent
            )
    return result


def days_since_last(
    points30: Sequence[dict[str, Any]], event_day: date, threshold: int
) -> int | None:
    qualifying = [
        _day(point)
        for point in points30
        if isinstance(point.get("score"), int | float) and point["score"] >= threshold
    ]
    return (event_day - max(qualifying)).days if qualifying else None


def event_day_metrics(points: Sequence[dict[str, Any]], event_day: date) -> dict[str, Any]:
    point = next((item for item in points if _day(item) == event_day), None)
    return {
        "event_day_anomaly_score": point.get("score") if point else None,
        "event_day_anomaly_level": point.get("level") if point else None,
        **{
            f"event_day_{name}": _metric(point, name) if point else None
            for name in ("event_count", "maximum_magnitude", "total_energy_joules", "mean_depth_km")
        },
    }


def catalog_adequacy(series: dict[str, Any], points: Sequence[dict[str, Any]]) -> dict[str, Any]:
    candidate = int(series.get("candidate_period_count") or 0)
    available = int(series.get("available_period_count") or 0)
    unavailable = int(series.get("unavailable_period_count") or max(candidate - available, 0))
    percentage = available / candidate * 100 if candidate else None
    event_days = sum((_metric(point, "event_count") or 0) > 0 for point in points)
    # Deterministic descriptive rule: >=90% usable, >=50% limited, otherwise insufficient.
    status = (
        "insufficient"
        if percentage is None or percentage < 50
        else ("usable" if percentage >= 90 else "limited")
    )
    return {
        "source_event_count": series.get("source_event_count"),
        "candidate_period_count": candidate,
        "available_period_count": available,
        "unavailable_period_count": unavailable,
        "availability_percentage": percentage,
        "days_with_one_or_more_catalog_events": event_days,
        "percentage_days_with_events": event_days / candidate * 100 if candidate else None,
        "status": status,
    }


def base_rates(points: Sequence[dict[str, Any]]) -> dict[str, Any]:
    scores = _numbers(point.get("score") for point in points)
    result: dict[str, Any] = {"total_scored_days": len(scores)}
    for threshold in THRESHOLDS:
        count = sum(score >= threshold for score in scores)
        result[f"days_ge{threshold}"] = count
        result[f"percentage_ge{threshold}"] = count / len(scores) * 100 if scores else None
    count100 = sum(score == 100 for score in scores)
    result.update(
        days_eq100=count100, percentage_eq100=count100 / len(scores) * 100 if scores else None
    )
    return result


def _associations_for_magnitude(
    points: Sequence[dict[str, Any]], magnitude: float
) -> dict[str, Any]:
    """Measure later-event associations for one explicit magnitude cutoff."""
    by_day = {_day(point): point for point in points}
    result: dict[str, Any] = {}
    for threshold in THRESHOLDS:
        qualifying = [
            point
            for point in points
            if isinstance(point.get("score"), int | float) and point["score"] >= threshold
        ]
        threshold_result: dict[str, Any] = {"qualifying_anomaly_day_count": len(qualifying)}
        for horizon in HORIZONS:
            count = sum(
                any(
                    (
                        _metric(
                            by_day.get(_day(point) + timedelta(days=offset), {}),
                            "maximum_magnitude",
                        )
                        or -math.inf
                    )
                    >= magnitude
                    for offset in range(1, horizon + 1)
                )
                for point in qualifying
            )
            threshold_result[f"followed_by_event_within_{horizon}d_count"] = count
            threshold_result[f"followed_by_event_within_{horizon}d_fraction"] = (
                count / len(qualifying) if qualifying else None
            )
        result[f"threshold_{threshold}"] = threshold_result
    return result


def future_event_associations(points: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Return comparable regional associations for the fixed M5, M6, and M7 cutoffs."""
    return {
        f"magnitude_ge{magnitude}": _associations_for_magnitude(points, magnitude)
        for magnitude in ASSOCIATION_MAGNITUDES
    }


def classify_regime(points14: Sequence[dict[str, Any]]) -> str:
    count = sum(
        isinstance(point.get("score"), int | float) and point["score"] >= 70 for point in points14
    )
    if count == 0:
        return "quiet"
    if count == 1:
        return "isolated_anomaly"
    if longest_run(points14, 70) >= 3:
        return "persistent_anomalous_regime"
    return "intermittent_anomalies"


def anchor_features(points: Sequence[dict[str, Any]], anchor_day: date) -> dict[str, Any]:
    """Calculate the shared, strictly pre-anchor features for a case or control."""
    windows = {days: window_points(points, anchor_day, days) for days in (30, 14, 7)}
    persistence = persistence_metrics(windows[30], anchor_day)
    recency = {
        f"days_since_last_score_{threshold}": days_since_last(
            windows[30], anchor_day, threshold
        )
        for threshold in (70, 75, 80, 90)
    }
    persistence.update(recency)
    return {
        "pre30": window_metrics(windows[30]),
        "pre14": window_metrics(windows[14]),
        "pre7": window_metrics(windows[7]),
        "persistence": persistence,
        "recency": recency,
        "regime_classification": classify_regime(windows[14]),
    }


def eligible_control_dates(points: Sequence[dict[str, Any]]) -> list[date]:
    """Return anchors with complete prior history and no M7+ day within ±30 days."""
    point_days = {_day(point) for point in points}
    major_days = {
        _day(point)
        for point in points
        if (_metric(point, "maximum_magnitude") or -math.inf) >= 7.0
    }
    eligible = []
    for anchor in sorted(point_days):
        # Coverage is explicit: each of the 30 preceding UTC dates must exist.
        if any(anchor - timedelta(days=offset) not in point_days for offset in range(1, 31)):
            continue
        if any(abs((anchor - major).days) <= CONTROL_EXCLUSION_DAYS for major in major_days):
            continue
        eligible.append(anchor)
    return eligible


def sample_control_dates(
    points: Sequence[dict[str, Any]],
    count: int,
    seed: int,
    non_overlapping: bool = False,
) -> list[date]:
    """Sample controls without consulting anomaly scores."""
    if count == 0:
        return []
    candidates = eligible_control_dates(points)
    random.Random(seed).shuffle(candidates)
    selected: list[date] = []
    for candidate in candidates:
        if non_overlapping and any(abs((candidate - other).days) < 30 for other in selected):
            continue
        selected.append(candidate)
        if len(selected) == count:
            break
    return sorted(selected)


def controls_payload(
    benchmark: dict[str, Any],
    points: Sequence[dict[str, Any]],
    count: int,
    seed: int,
    non_overlapping: bool = False,
    adequacy: str = "usable",
) -> dict[str, Any]:
    selected = sample_control_dates(points, count, seed, non_overlapping)
    controls = [
        {"control_date": str(anchor), **anchor_features(points, anchor)} for anchor in selected
    ]
    return {
        "benchmark_id": benchmark["benchmark_id"],
        "region_key": benchmark["region_key"],
        "seed": seed,
        "requested_control_count": count,
        "selected_control_count": len(controls),
        "selection_status": (
            "complete" if len(controls) == count else "insufficient_eligible_controls"
        ),
        "catalog_adequacy": adequacy,
        "non_overlapping_controls": non_overlapping,
        "exclusion_rule": (
            "Control anchors require 30 complete preceding days and exclude dates within "
            "30 days before or after (inclusive) any M7.0+ day in maximum_magnitude."
        ),
        "controls": controls,
    }


def analyze(benchmark: dict[str, Any], series: dict[str, Any]) -> dict[str, Any]:
    points = series.get("anomaly_results", [])
    event_day = date.fromisoformat(benchmark["event_date_utc"])
    features = anchor_features(points, event_day)
    return {
        "benchmark": benchmark,
        "catalog_adequacy": catalog_adequacy(series, points),
        "event_day_metrics": event_day_metrics(points, event_day),
        "pre_event_windows": {
            f"{days}_day": features[f"pre{days}"] for days in (30, 14, 7)
        },
        "persistence_metrics": features["persistence"],
        "regional_base_rates": base_rates(points),
        "future_event_associations": future_event_associations(points),
        "benchmark_magnitude_associations": {
            "required_magnitude": float(benchmark["event_magnitude"]),
            "associations": _associations_for_magnitude(
                points, float(benchmark["event_magnitude"])
            ),
        },
        "regime_characterization": {
            "classification": features["regime_classification"],
            "definition": (
                "quiet: 0 >=70 days in 14d; isolated: 1; intermittent: 2+ with "
                "run <3; persistent: run >=3"
            ),
        },
        "research_only": True,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


COMPARISON_FEATURES = {
    **{
        f"pre{days}_mean_score": (f"pre{days}", "mean_anomaly_score")
        for days in (30, 14, 7)
    },
    **{
        f"pre{days}_days_ge{threshold}": (f"pre{days}", f"days_ge{threshold}")
        for days in (30, 14, 7)
        for threshold in (70, 80)
    },
    "pre30_max_score": ("pre30", "maximum_anomaly_score"),
    "longest_consecutive_run_ge70": ("persistence", "longest_consecutive_run_ge70"),
    "longest_consecutive_run_ge80": ("persistence", "longest_consecutive_run_ge80"),
    **{
        f"days_since_last_score_{threshold}": (
            "recency",
            f"days_since_last_score_{threshold}",
        )
        for threshold in (70, 80, 90)
    },
}


def _feature_value(features: dict[str, Any], path: tuple[str, str]) -> Any:
    return features[path[0]][path[1]]


def numeric_comparison(case_value: Any, control_values: Sequence[Any]) -> dict[str, Any]:
    """Return descriptive empirical statistics while preserving null counts."""
    values = _numbers(control_values)
    total = len(control_values)
    result = {
        "case_value": case_value,
        "control_count": total,
        "valid_control_count": len(values),
        "null_control_count": total - len(values),
        "control_mean": statistics.fmean(values) if values else None,
        "control_median": statistics.median(values) if values else None,
        "control_standard_deviation": statistics.pstdev(values) if values else None,
        "case_percentile_rank": None,
        "fraction_of_controls_ge_case": None,
    }
    if isinstance(case_value, int | float) and values:
        result["case_percentile_rank"] = (
            100 * sum(value <= case_value for value in values) / len(values)
        )
        result["fraction_of_controls_ge_case"] = (
            sum(value >= case_value for value in values) / len(values)
        )
    return result


def compare_case_controls(
    case_features: dict[str, Any], controls: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    comparisons = {
        name: numeric_comparison(
            _feature_value(case_features, path),
            [_feature_value(control, path) for control in controls],
        )
        for name, path in COMPARISON_FEATURES.items()
    }
    counts = Counter(control["regime_classification"] for control in controls)
    total = len(controls)
    case_regime = case_features["regime_classification"]
    return {
        "numeric_features": comparisons,
        "regimes": {
            "case_regime": case_regime,
            "control_distribution": {
                regime: counts[regime] / total if total else None for regime in REGIMES
            },
        },
        "retrospective_nonpredictive": True,
    }


def summary_row(result: dict[str, Any]) -> dict[str, Any]:
    bench, windows, persistence = (
        result["benchmark"],
        result["pre_event_windows"],
        result["persistence_metrics"],
    )
    row = {
        "benchmark_id": bench["benchmark_id"],
        "region_key": bench["region_key"],
        "event_date": bench["event_date_utc"],
        "event_magnitude": bench["event_magnitude"],
    }
    for days in (30, 14, 7):
        metrics = windows[f"{days}_day"]
        row.update(
            {
                f"pre{days}_mean_score": metrics["mean_anomaly_score"],
                f"pre{days}_days_ge70": metrics["days_ge70"],
                f"pre{days}_days_ge80": metrics["days_ge80"],
            }
        )
    row.update(
        pre30_max_score=windows["30_day"]["maximum_anomaly_score"],
        longest_ge70_run=persistence["longest_consecutive_run_ge70"],
        event_day_score=result["event_day_metrics"]["event_day_anomaly_score"],
        regime_classification=result["regime_characterization"]["classification"],
        catalog_adequacy=result["catalog_adequacy"]["status"],
    )
    row.update(
        {
            f"days_since_last_{t}": persistence[f"days_since_last_score_{t}"]
            for t in (70, 75, 80, 90)
        }
    )
    validation = result.get("control_validation")
    if validation:
        numeric = validation["numeric_features"]
        regimes = validation["regimes"]
        distribution = regimes["control_distribution"]
        row.update(
            control_count=numeric["pre30_mean_score"]["control_count"],
            pre30_mean_percentile=numeric["pre30_mean_score"]["case_percentile_rank"],
            pre14_mean_percentile=numeric["pre14_mean_score"]["case_percentile_rank"],
            pre7_mean_percentile=numeric["pre7_mean_score"]["case_percentile_rank"],
            pre30_ge70_percentile=numeric["pre30_days_ge70"]["case_percentile_rank"],
            pre14_ge70_percentile=numeric["pre14_days_ge70"]["case_percentile_rank"],
            pre7_ge70_percentile=numeric["pre7_days_ge70"]["case_percentile_rank"],
            pre30_max_percentile=numeric["pre30_max_score"]["case_percentile_rank"],
            longest_ge70_run_percentile=numeric["longest_consecutive_run_ge70"][
                "case_percentile_rank"
            ],
            case_regime=regimes["case_regime"],
            control_fraction_same_regime=distribution[regimes["case_regime"]],
            control_fraction_persistent_regime=distribution["persistent_anomalous_regime"],
        )
    return row


def run_benchmarks(
    ids: Sequence[str] | None,
    output: Path = DEFAULT_OUTPUT,
    config_path: Path | None = None,
    research_root: Path | None = None,
    controls_per_benchmark: int = 100,
    seed: int = 42,
    non_overlapping_controls: bool = False,
) -> list[dict[str, Any]]:
    config_path = config_path or CONFIG_PATH
    research_root = research_root or RESEARCH_ROOT
    configured = json.loads(config_path.read_text(encoding="utf-8"))["benchmarks"]
    selected = (
        configured if ids is None else [item for item in configured if item["benchmark_id"] in ids]
    )
    if ids is not None and len(selected) != len(ids):
        missing = sorted(set(ids) - {item["benchmark_id"] for item in selected})
        raise ValueError(f"Unknown benchmark(s): {', '.join(missing)}")
    results = []
    for benchmark in selected:
        artifact = research_root / benchmark["region_key"] / "timeseries.json"
        if not artifact.exists():
            command = (
                f"python -m app.research --region {benchmark['region_key']} "
                f"--start {benchmark['analysis_start']} --end {benchmark['analysis_end']}"
            )
            raise FileNotFoundError(f"Missing research artifact {artifact}. Run: {command}")
        series = json.loads(artifact.read_text(encoding="utf-8"))
        result = analyze(benchmark, series)
        adequacy = result["catalog_adequacy"]["status"]
        if adequacy == "insufficient":
            raise ValueError(
                f"Benchmark {benchmark['benchmark_id']} has insufficient catalog adequacy; "
                "control generation was not performed"
            )
        controls = controls_payload(
            benchmark,
            series.get("anomaly_results", []),
            controls_per_benchmark,
            seed,
            non_overlapping_controls,
            adequacy,
        )
        event_day = date.fromisoformat(benchmark["event_date_utc"])
        result["control_validation"] = compare_case_controls(
            anchor_features(series.get("anomaly_results", []), event_day), controls["controls"]
        )
        _write_json(output / benchmark["benchmark_id"] / "result.json", result)
        _write_json(output / benchmark["benchmark_id"] / "controls.json", controls)
        results.append(result)
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure historical associations in frozen Athena research artifacts (nonpredictive)."
        )
    )
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--benchmark", help="Configured benchmark ID")
    choice.add_argument("--all", action="store_true", help="Run every configured benchmark")
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT, help="Output root (default: data/benchmarks)"
    )
    parser.add_argument(
        "--controls-per-benchmark", type=int, default=100, help="Controls to sample (default: 100)"
    )
    parser.add_argument("--seed", type=int, default=42, help="Deterministic sampling seed")
    parser.add_argument(
        "--non-overlapping-controls",
        action="store_true",
        help="Require selected control anchor dates to be at least 30 days apart",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.controls_per_benchmark < 0:
            parser.error("--controls-per-benchmark must be nonnegative")
        results = run_benchmarks(
            None if args.all else [args.benchmark],
            args.output,
            controls_per_benchmark=args.controls_per_benchmark,
            seed=args.seed,
            non_overlapping_controls=args.non_overlapping_controls,
        )
        if args.all:
            rows = [summary_row(result) for result in results]
            _write_json(args.output / "summary.json", rows)
            args.output.mkdir(parents=True, exist_ok=True)
            with (args.output / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else [])
                writer.writeheader()
                writer.writerows(rows)
            _write_json(args.output / "validation_summary.json", rows)
            with (args.output / "validation_summary.csv").open(
                "w", newline="", encoding="utf-8"
            ) as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else [])
                writer.writeheader()
                writer.writerows(rows)
    except Exception as exc:
        parser.exit(1, f"Benchmark run failed: {exc}\n")


if __name__ == "__main__":
    main()
