from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.schemas.common import ErrorResponse
from app.services.athena import AthenaService, get_athena_service

router = APIRouter(tags=["analytics"])


@router.get(
    "/observatory",
    responses={503: {"model": ErrorResponse}},
    summary="Return Athena's complete historical intelligence report (nonpredictive)",
)
def observatory(
    service: Annotated[AthenaService, Depends(get_athena_service)],
) -> dict[str, Any]:
    return service.build_report().to_dict()
