from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.schemas.common import ErrorResponse, StatusResponse
from app.services.athena import AthenaService, get_athena_service

router = APIRouter(tags=["analytics"])


def _status_from_report(data: dict[str, Any]) -> StatusResponse:
    anomaly = data.get("latest_anomaly") or {}
    trend = data["time_series"]["trend"]
    catalog = data["catalog"]
    region = data["region"]
    return StatusResponse(
        region_key=region["key"],
        region_name=region["name"],
        overall_status=data["overall_status"],
        catalog_as_of_utc=catalog["as_of_utc"],
        source_event_count=catalog["source_event_count"],
        latest_anomaly_score=anomaly.get("score"),
        latest_anomaly_level=anomaly.get("level"),
        trend_direction=trend["direction"],
        trend_strength=trend["strength"],
        report_is_nonpredictive=data["report_is_nonpredictive"],
    )


@router.get(
    "/status",
    response_model=StatusResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Summarize historical observatory status (nonpredictive)",
)
def status(
    service: Annotated[AthenaService, Depends(get_athena_service)],
) -> StatusResponse:
    return _status_from_report(service.build_report().to_dict())
