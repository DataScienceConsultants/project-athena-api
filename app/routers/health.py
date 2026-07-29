from fastapi import APIRouter

from app.config import get_settings
from app.schemas.common import HealthResponse

router = APIRouter(tags=["service"])


@router.get("/health", response_model=HealthResponse, summary="Check service health")
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="healthy", service="project-athena-api", version=settings.api_version
    )
