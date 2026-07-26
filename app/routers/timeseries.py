from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.schemas.common import ErrorResponse
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
