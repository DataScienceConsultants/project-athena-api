from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.schemas.common import ErrorResponse, StatusResponse
from app.services.athena import AthenaService, get_athena_service

router = APIRouter(tags=["analytics"])


def _status_from_report(data: dict[str, Any]) -> StatusResponse:
    observatory = data.get("observatory") or {}
    metadata = data.get("metadata") or {}
    snapshot = data.get("snapshot") or {}
    anomaly = data.get("latest_anomaly") or snapshot.get("latest_anomaly") or {}
    trend = data["time_series"]["trend"]
    catalog = data.get("catalog") or observatory["catalog"]
    region = data.get("region") or {
        "key": catalog["region_key"],
        "name": catalog["region_name"],
    }
    return StatusResponse(
        region_key=region["key"],
        region_name=region["name"],
        overall_status=data.get("overall_status") or observatory["status"]["overall_status"],
        catalog_as_of_utc=catalog.get("as_of_utc") or metadata["catalog_as_of_utc"],
        source_event_count=catalog.get("source_event_count") or metadata["source_event_count"],
        latest_anomaly_score=anomaly.get("score"),
        latest_anomaly_level=anomaly.get("level"),
        trend_direction=trend["direction"],
        trend_strength=trend["strength"],
        report_is_nonpredictive=data.get("report_is_nonpredictive")
        or metadata["report_is_nonpredictive"],
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
