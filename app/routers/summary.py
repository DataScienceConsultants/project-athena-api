"""Frontend-ready projection of Athena's public Observatory serialization."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.schemas.common import ErrorResponse, SummaryResponse
from app.services.athena import AthenaService, get_athena_service

router = APIRouter(tags=["analytics"])


def _summary_from_report(data: dict[str, Any]) -> SummaryResponse:
    """Select delivery fields without reproducing any scientific calculation."""
    anomaly = data.get("latest_anomaly") or {}
    swarm = data.get("swarm") or {}
    trend = data["time_series"]["trend"]
    catalog = data["catalog"]
    region = data["region"]
    return SummaryResponse(
        region_key=region["key"],
        region_name=region["name"],
        overall_status=data["overall_status"],
        catalog_as_of_utc=catalog["as_of_utc"],
        source_event_count=catalog["source_event_count"],
        latest_anomaly_score=anomaly.get("score"),
        latest_anomaly_level=anomaly.get("level"),
        trend_direction=trend["direction"],
        trend_strength=trend["strength"],
        swarm_count=swarm.get("count"),
        executive_summary=data["executive_summary"],
        disclaimer=data["disclaimer"],
        report_is_nonpredictive=data["report_is_nonpredictive"],
    )


@router.get(
    "/summary",
    response_model=SummaryResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Return a frontend-ready historical Observatory summary (nonpredictive)",
)
def summary(
    service: Annotated[AthenaService, Depends(get_athena_service)],
) -> SummaryResponse:
    # Serialize once as the sole source for every field in this API-owned view.
    data = service.build_report().to_dict()
    return _summary_from_report(data)
