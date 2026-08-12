from datetime import date, timedelta

import pytest

from app.sequences import analyze_sequence, discover_sequences, magnitude_class


def event(day, magnitude, suffix="1"):
    return {
        "event_timestamp": f"{day}T00:00:00Z",
        "event_id": suffix,
        "magnitude": magnitude,
    }


def point(day, score=50, count=1, magnitude=2, energy=None):
    return {
        "current_start": f"{day}T00:00:00Z",
        "score": score,
        "metric_scores": {
            "event_count": {"current_value": count},
            "maximum_magnitude": {"current_value": magnitude},
            "total_energy_joules": {"current_value": energy},
            "mean_depth_km": {"current_value": 10},
        },
    }


@pytest.mark.parametrize(
    ("magnitude", "expected"),
    [(5.9, None), (6, "strong"), (6.9, "strong"), (7, "major"), (7.9, "major"), (8, "great")],
)
def test_magnitude_classification(magnitude, expected):
    assert magnitude_class(magnitude) == expected


def test_recursive_discovery_ignores_nonqualifying_and_separates_quiet_year():
    events = [
        event("2020-01-01", 6),
        event("2020-06-01", 5.9),
        event("2020-12-31", 7),
        event("2021-12-30", 8),
        event("2023-01-01", 6),
    ]
    groups = discover_sequences(events)
    assert [len(group) for group in groups] == [3, 1]


def test_same_day_events_are_retained():
    assert (
        len(discover_sequences([event("2020-01-01", 6, "a"), event("2020-01-01", 7, "b")])[0]) == 2
    )


def test_boundaries_censoring_monthly_between_and_post_coverage():
    first = date(2021, 1, 1)
    second = first + timedelta(days=47)
    points = [
        point(first - timedelta(days=365) + timedelta(days=i), score=70 + i % 2) for i in range(500)
    ]
    result = analyze_sequence(
        [event(first.isoformat(), 7.5), event(second.isoformat(), 7.4)],
        points,
        "test",
        first - timedelta(days=365),
        second + timedelta(days=90),
    )
    assert result["requested_sequence_start"] == "2020-01-02"
    assert result["requested_sequence_end"] == "2022-02-18"
    assert result["pre_event_coverage_complete"] is True
    assert result["sequence_closed"] is False
    assert result["censoring_status"] == "ongoing_or_right_censored"
    assert result["major_event_count"] == 2
    assert result["between_event_analysis"][0]["days_between_events"] == 47
    assert set(result["subsequent_event_pre_windows"][0]["pre_event_windows"]) == {"7", "14", "30"}
    assert result["monthly_pre_event"]
    assert result["post_event_evolution"][1]["windows"]["90"]["coverage_complete"] is True
    assert result["post_event_evolution"][1]["windows"]["180"]["metrics"] is None


def test_closed_requires_observed_quiet_year_and_left_censoring_is_reported():
    day = date(2020, 1, 1)
    points = [point(day + timedelta(days=i)) for i in range(-10, 366)]
    result = analyze_sequence(
        [event(day.isoformat(), 6.4)],
        points,
        "x",
        day - timedelta(days=10),
        day + timedelta(days=365),
    )
    assert result["sequence_closed"] is True
    assert result["post_event_coverage_complete"] is True
    assert result["pre_event_coverage_complete"] is False
    assert result["censoring_status"] == "left_censored"
