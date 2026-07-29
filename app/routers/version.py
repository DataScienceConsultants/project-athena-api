import platform

from fastapi import APIRouter

from app.config import get_settings
from app.schemas.common import VersionResponse

router = APIRouter(tags=["service"])


@router.get("/version", response_model=VersionResponse, summary="Show component versions")
def version() -> VersionResponse:
    settings = get_settings()
    return VersionResponse(
        api_version=settings.api_version,
        athena_version=settings.athena_version,
        python_version=platform.python_version(),
    )
