"""Retrospective, research-only analysis of M6+ seismic sequences."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

RESEARCH_ROOT = Path("data/research")
OUTPUT_ROOT = Path("data/sequences")
TRIGGER_MAGNITUDE = 6.0
SEQUENCE_DAYS = 365
WINDOWS = (7, 14, 30, 60, 90, 180, 365)


def magnitude_class(magnitude: float) -> str | None:
    """Return the frozen research terminology for an earthquake magnitude."""
    if magnitude < 6:
        return None
    if magnitude < 7:
        return "strong"
    if magnitude < 8:
        return "major"
    return "great"


classify_magnitude = magnitude_class


def _date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _timestamp(event: dict[str, Any]) -> str:
    value = event.get("event_timestamp") or event.get("event_time_utc")
    if not isinstance(value, str):
        raise ValueError("Catalog event is missing event_timestamp/event_time_utc")
    return value


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _metric(point: dict[str, Any], name: str) -> float | None:
    value = point.get("metric_scores", {}).get(name)
    return _number(value.get("current_value")) if isinstance(value, dict) else None


def _values(values: Iterable[Any]) -> list[float]:
    return [number for value in values if (number := _number(value)) is not None]


def _summary(points: Sequence[dict[str, Any]]) -> dict[str, Any]:
    scores = _values(point.get("score") for point in points)
    result: dict[str, Any] = {
        "scored_days": len(scores),
        "mean_anomaly_score": statistics.fmean(scores) if scores else None,
        "median_anomaly_score": statistics.median(scores) if scores else None,
        "maximum_anomaly_score": max(scores) if scores else None,
        "standard_deviation_anomaly_score": statistics.pstdev(scores) if scores else None,
    }
    for threshold in (70, 75, 80, 90, 95):
        result[f"days_ge{threshold}"] = sum(score >= threshold for score in scores)
    result["days_eq100"] = sum(score == 100 for score in scores)
    for metric in ("event_count", "maximum_magnitude", "total_energy_joules"):
        values = _values(_metric(point, metric) for point in points)
        result[f"mean_{metric}"] = statistics.fmean(values) if values else None
        result[f"maximum_{metric}"] = max(values) if values else None
    depths = _values(_metric(point, "mean_depth_km") for point in points)
    result["mean_depth_km"] = statistics.fmean(depths) if depths else None
    return result


def _range(points: Sequence[dict[str, Any]], start: date, end: date, *, inclusive=False):
    return [
        p for p in points if start <= _date(p["current_start"]) < end + timedelta(days=inclusive)
    ]


def discover_sequences(events: Sequence[dict[str, Any]], threshold: float = 6.0):
    """Group qualifying catalog events using recursive 365-day extension."""
    qualifying = sorted(
        (event for event in events if (_number(event.get("magnitude")) or -math.inf) >= threshold),
        key=lambda event: (_timestamp(event), event.get("event_id", "")),
    )
    groups: list[list[dict[str, Any]]] = []
    for event in qualifying:
        event_day = _date(_timestamp(event))
        # The frozen extension interval is half-open: an event at the endpoint
        # starts a new sequence rather than extending the current sequence.
        if not groups or event_day >= _date(_timestamp(groups[-1][-1])) + timedelta(
            days=SEQUENCE_DAYS
        ):
            groups.append([event])
        else:
            groups[-1].append(event)
    return groups


def monthly_pre_event(points: Sequence[dict[str, Any]], event_day: date):
    selected = _range(points, event_day - timedelta(days=365), event_day)
    months: dict[str, list[dict[str, Any]]] = {}
    for point in selected:
        months.setdefault(_date(point["current_start"]).strftime("%Y-%m"), []).append(point)
    rows = []
    for month, month_points in sorted(months.items()):
        summary = _summary(month_points)
        rows.append(
            {
                "month": month,
                "scored_days": summary["scored_days"],
                "mean_anomaly_score": summary["mean_anomaly_score"],
                "median_anomaly_score": summary["median_anomaly_score"],
                "maximum_anomaly_score": summary["maximum_anomaly_score"],
                "days_ge70": summary["days_ge70"],
                "days_ge80": summary["days_ge80"],
                "days_ge90": summary["days_ge90"],
                "event_count_total": sum(_values(_metric(p, "event_count") for p in month_points)),
                "maximum_magnitude": summary["maximum_maximum_magnitude"],
                "total_energy_joules": sum(
                    _values(_metric(p, "total_energy_joules") for p in month_points)
                )
                or None,
            }
        )
    return rows


def _event_record(
    event: dict[str, Any], points_by_day: dict[date, dict[str, Any]], previous, next_
):
    magnitude = float(event["magnitude"])
    day = _date(event["event_timestamp"])
    record = {
        "event_date": day.isoformat(),
        "event_timestamp": event["event_timestamp"],
        "magnitude": magnitude,
        "magnitude_class": magnitude_class(magnitude),
        "latitude": _number(event.get("latitude")),
        "longitude": _number(event.get("longitude")),
        "depth_km": _number(event.get("depth_km")),
        "athena_event_day_anomaly_score": points_by_day.get(day, {}).get("score"),
        "days_since_previous_qualifying_event": (day - _date(previous["event_timestamp"])).days
        if previous
        else None,
        "days_until_next_qualifying_event": (_date(next_["event_timestamp"]) - day).days
        if next_
        else None,
        "days_since_previous_M6_plus": (day - _date(previous["event_timestamp"])).days
        if previous
        else None,
        "previous_event_magnitude": float(previous["magnitude"]) if previous else None,
        "previous_event_magnitude_class": magnitude_class(float(previous["magnitude"]))
        if previous
        else None,
        "phase": "qualifying_event",
    }
    for window in (30, 60, 90, 180, 365):
        record[f"previous_M6_plus_within_{window}_days"] = sum(
            _date(event["event_timestamp"]) - timedelta(days=window)
            <= _date(item["event_timestamp"])
            < day
            for item in getattr(_event_record, "all_events", [])
        )
    return record


def analyze_sequence(group, points, region_key, artifact_start: date, artifact_end: date, index=1):
    first_day, last_day = _date(group[0]["event_timestamp"]), _date(group[-1]["event_timestamp"])
    requested_start, requested_end = first_day - timedelta(days=365), last_day + timedelta(days=365)
    observed_start, observed_end = (
        max(requested_start, artifact_start),
        min(requested_end, artifact_end),
    )
    by_day = {_date(point["current_start"]): point for point in points}
    _event_record.all_events = group
    records = [
        _event_record(
            e, by_day, group[i - 1] if i else None, group[i + 1] if i + 1 < len(group) else None
        )
        for i, e in enumerate(group)
    ]
    pre = {
        str(days): _summary(_range(points, first_day - timedelta(days=days), first_day))
        for days in WINDOWS
    }
    between = []
    subsequent = []
    for previous, current in zip(group, group[1:], strict=False):
        left, right = _date(previous["event_timestamp"]), _date(current["event_timestamp"])
        metrics = _summary(_range(points, left + timedelta(days=1), right))
        between.append(
            {
                "previous_event_date": left.isoformat(),
                "previous_event_magnitude": float(previous["magnitude"]),
                "next_event_date": right.isoformat(),
                "next_event_magnitude": float(current["magnitude"]),
                "days_between_events": (right - left).days,
                "between_period_mean_anomaly_score": metrics["mean_anomaly_score"],
                "between_period_max_anomaly_score": metrics["maximum_anomaly_score"],
                "days_ge70": metrics["days_ge70"],
                "days_ge80": metrics["days_ge80"],
                "days_ge90": metrics["days_ge90"],
                "event_count": sum(
                    _values(
                        _metric(p, "event_count")
                        for p in _range(points, left + timedelta(days=1), right)
                    )
                )
                or None,
                "maximum_intermediate_magnitude": metrics["maximum_maximum_magnitude"],
                "total_energy": sum(
                    _values(
                        _metric(p, "total_energy_joules")
                        for p in _range(points, left + timedelta(days=1), right)
                    )
                )
                or None,
                "phase": "between_qualifying_events",
            }
        )
        subsequent.append(
            {
                "event_date": right.isoformat(),
                "pre_event_windows": {
                    str(d): _summary(_range(points, right - timedelta(days=d), right))
                    for d in (7, 14, 30)
                },
            }
        )
    post = []
    for event in group:
        day = _date(event["event_timestamp"])
        windows = {}
        for days in WINDOWS:
            complete = artifact_end >= day + timedelta(days=days)
            windows[str(days)] = {
                "coverage_complete": complete,
                "metrics": _summary(
                    _range(
                        points, day + timedelta(days=1), day + timedelta(days=days), inclusive=True
                    )
                )
                if complete
                else None,
            }
        post.append({"event_date": day.isoformat(), "windows": windows})
    counts = {
        name: sum(r["magnitude_class"] == name for r in records)
        for name in ("strong", "major", "great")
    }
    closed = artifact_end >= requested_end
    sequence_id = f"{region_key}-{first_day.isoformat()}-{index:03d}"
    return {
        "sequence_id": sequence_id,
        "region_key": region_key,
        "first_qualifying_event": records[0],
        "last_observed_qualifying_event": records[-1],
        "qualifying_event_count": len(records),
        **{f"{k}_event_count": v for k, v in counts.items()},
        "requested_sequence_start": requested_start.isoformat(),
        "requested_sequence_end": requested_end.isoformat(),
        "observed_sequence_start": observed_start.isoformat(),
        "observed_sequence_end": observed_end.isoformat(),
        "pre_event_coverage_complete": artifact_start <= requested_start,
        "post_event_coverage_complete": closed,
        "sequence_closed": closed,
        "censoring_status": "complete"
        if closed and artifact_start <= requested_start
        else ("ongoing_or_right_censored" if not closed else "left_censored"),
        "sequence_duration_days_observed": max((observed_end - observed_start).days, 0),
        "events": records,
        "pre_first_event_windows": pre,
        "monthly_pre_event": monthly_pre_event(points, first_day),
        "between_event_analysis": between,
        "subsequent_event_pre_windows": subsequent,
        "post_event_evolution": post,
    }


def _load(region: str, root: Path):
    directory = root / region
    required = (directory / "catalog.csv", directory / "timeseries.json")
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        command = f"python -m app.research --region {region} --start YYYY-MM-DD --end YYYY-MM-DD"
        raise FileNotFoundError(f"Missing research artifacts: {', '.join(missing)}. Run: {command}")
    with required[0].open(newline="", encoding="utf-8") as source:
        events = [
            {**row, "event_timestamp": row["event_time_utc"]} for row in csv.DictReader(source)
        ]
    series = json.loads(required[1].read_text(encoding="utf-8"))
    return events, series["anomaly_results"]


def _write_csv(path: Path, rows):
    rows = list(rows)
    with path.open("w", newline="", encoding="utf-8") as target:
        if rows:
            writer = csv.DictWriter(target, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def run(region: str, research_root=RESEARCH_ROOT, output_root=OUTPUT_ROOT, threshold=6.0):
    events, points = _load(region, Path(research_root))
    dates = [_date(point["current_start"]) for point in points]
    if not dates:
        raise ValueError("Research timeseries contains no observations")
    results = [
        analyze_sequence(group, points, region, min(dates), max(dates), i)
        for i, group in enumerate(discover_sequences(events, threshold), 1)
    ]
    destination = Path(output_root) / region
    destination.mkdir(parents=True, exist_ok=True)
    summaries = [
        {
            k: v
            for k, v in result.items()
            if k
            not in {
                "events",
                "pre_first_event_windows",
                "monthly_pre_event",
                "between_event_analysis",
                "subsequent_event_pre_windows",
                "post_event_evolution",
            }
        }
        for result in results
    ]
    (destination / "sequences.json").write_text(
        json.dumps(summaries, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(destination / "sequences.csv", summaries)
    for result in results:
        folder = destination / result["sequence_id"]
        folder.mkdir(exist_ok=True)
        (folder / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        _write_csv(folder / "monthly_pre_event.csv", result["monthly_pre_event"])
        _write_csv(folder / "events.csv", result["events"])
    return results


def build_parser():
    parser = argparse.ArgumentParser(
        description="Retrospective, nonpredictive Athena seismic sequence analysis"
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--region")
    selection.add_argument("--all", action="store_true")
    parser.add_argument(
        "--trigger-threshold",
        type=float,
        default=TRIGGER_MAGNITUDE,
        help="qualifying magnitude (default: 6.0)",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    regions = (
        [path.name for path in RESEARCH_ROOT.iterdir() if path.is_dir()]
        if args.all
        else [args.region]
    )
    try:
        for region in regions:
            run(region, threshold=args.trigger_threshold)
    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(f"Sequence analysis failed: {exc}") from exc


if __name__ == "__main__":
    main()
