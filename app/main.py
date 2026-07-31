"""FastAPI application factory and deterministic route registration."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import health, observatory, status, summary, timeseries, version
from app.schemas.common import DiscoveryResponse
from app.services.athena import AthenaReportUnavailableError

settings = get_settings()
app = FastAPI(
    title="Project Athena API",
    version="0.1.0",
    description=(
        "A deterministic delivery layer for Project Athena historical seismic analytics. "
        "Results are nonpredictive and do not estimate future earthquake probability."
    ),
    contact={"name": "Data Science Consultants"},
    license_info={"name": "See repository license"},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.exception_handler(AthenaReportUnavailableError)
async def report_unavailable_handler(
    request: Request, exc: AthenaReportUnavailableError
) -> JSONResponse:
    logging.getLogger(__name__).error("Athena report unavailable for %s", request.url.path)
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "athena_report_unavailable",
                "message": "The Observatory intelligence report is currently unavailable.",
            }
        },
    )


@app.get("/", response_model=DiscoveryResponse, tags=["service"], summary="Discover the service")
def root() -> DiscoveryResponse:
    return DiscoveryResponse(
        service="project-athena-api",
        version=settings.api_version,
        endpoints={
            "health": "/health",
            "version": "/version",
            "status": "/status",
            "summary": "/summary",
            "observatory": "/observatory",
            "timeseries": "/timeseries",
        },
    )


app.include_router(health.router)
app.include_router(version.router)
app.include_router(status.router)
app.include_router(summary.router)
app.include_router(observatory.router)
app.include_router(timeseries.router)
