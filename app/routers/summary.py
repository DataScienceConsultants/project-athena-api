"""Frontend-ready projection of Athena's public Observatory serialization."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.schemas.common import ErrorResponse, SummaryResponse
from app.services.athena import AthenaService, get_athena_service

router = APIRouter(tags=["analytics"])


def _summary_from_report(data: dict[str, Any]) -> SummaryResponse:
    """Select delivery fields without reproducing any scientific calculation."""
    observatory = data.get("observatory") or {}
    metadata = data.get("metadata") or {}
    snapshot = data.get("snapshot") or {}
    anomaly = data.get("latest_anomaly") or snapshot.get("latest_anomaly") or {}
    swarm = data.get("swarm") or observatory.get("swarm") or {}
    trend = data["time_series"]["trend"]
    catalog = data.get("catalog") or observatory["catalog"]
    region = data.get("region") or {
        "key": catalog["region_key"],
        "name": catalog["region_name"],
    }
    return SummaryResponse(
        region_key=region["key"],
        region_name=region["name"],
        overall_status=data.get("overall_status") or observatory["status"]["overall_status"],
        catalog_as_of_utc=catalog.get("as_of_utc") or metadata["catalog_as_of_utc"],
        source_event_count=catalog.get("source_event_count") or metadata["source_event_count"],
        latest_anomaly_score=anomaly.get("score"),
        latest_anomaly_level=anomaly.get("level"),
        trend_direction=trend["direction"],
        trend_strength=trend["strength"],
        swarm_count=swarm.get("count"),
        executive_summary=data["executive_summary"],
        disclaimer=data["disclaimer"],
        report_is_nonpredictive=data.get("report_is_nonpredictive")
        or metadata["report_is_nonpredictive"],
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
