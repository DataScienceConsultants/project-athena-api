from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.schemas.common import ChartPoint, ChartTimeseriesResponse, ErrorResponse
from app.services.athena import AthenaService, get_athena_service

router = APIRouter(tags=["analytics"])


@router.get(
    "/timeseries",
    responses={503: {"model": ErrorResponse}},
    summary="Return Athena's historical time series (nonpredictive)",
)
def timeseries(
    service: Annotated[AthenaService, Depends(get_athena_service)],
) -> dict[str, Any]:
    return service.build_report().to_dict()["time_series"]


def _current_metric_value(anomaly: dict[str, Any], name: str) -> float | None:
    metric = anomaly.get("metric_scores", {}).get(name)
    return metric.get("current_value") if metric is not None else None


@router.get(
    "/timeseries/chart",
    response_model=ChartTimeseriesResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Return compact Athena historical chart data",
)
def chart_timeseries(
    service: Annotated[AthenaService, Depends(get_athena_service)],
    days: Annotated[int | None, Query(gt=0)] = None,
) -> ChartTimeseriesResponse:
    """Project the unified report's anomaly results without recalculating them."""
    time_series = service.build_report().to_dict()["time_series"]
    anomalies = time_series["anomaly_results"]
    if days is not None:
        anomalies = anomalies[-days:]

    return ChartTimeseriesResponse(
        analysis_start=time_series["analysis_start"],
        analysis_end=time_series["analysis_end"],
        frequency=time_series["frequency"],
        source_event_count=time_series["source_event_count"],
        available_period_count=time_series["available_period_count"],
        points=[
            ChartPoint(
                date=anomaly["current_start"].split("T", maxsplit=1)[0],
                anomaly_score=anomaly["score"],
                anomaly_level=anomaly["level"],
                event_count=_current_metric_value(anomaly, "event_count"),
                maximum_magnitude=_current_metric_value(anomaly, "maximum_magnitude"),
                total_energy_joules=_current_metric_value(anomaly, "total_energy_joules"),
                mean_depth_km=_current_metric_value(anomaly, "mean_depth_km"),
            )
            for anomaly in anomalies
        ],
    )
