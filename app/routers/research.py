"""Read-only routes for prepared Athena global-research artifacts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import get_settings
from app.services.research_artifacts import ResearchArtifactService

router = APIRouter(prefix="/research", tags=["research"])


def get_research_artifact_service() -> ResearchArtifactService:
    """Build the read-only artifact delivery service from environment-backed settings."""
    return ResearchArtifactService(get_settings().research_bundle_path)


ResearchService = Annotated[ResearchArtifactService, Depends(get_research_artifact_service)]


@router.get("/global/summary", summary="Describe the prepared global research cohort")
def global_summary(service: ResearchService) -> dict:
    return service.summary()


@router.get("/earthquakes", summary="Read prepared global research earthquakes")
def earthquakes(
    service: ResearchService,
    start: datetime | None = None,
    end: datetime | None = None,
    minimum_magnitude: Annotated[float, Query(ge=-2.0)] = 6.0,
    min_latitude: Annotated[float | None, Query(ge=-90.0, le=90.0)] = None,
    max_latitude: Annotated[float | None, Query(ge=-90.0, le=90.0)] = None,
    min_longitude: Annotated[float | None, Query(ge=-180.0, le=180.0)] = None,
    max_longitude: Annotated[float | None, Query(ge=-180.0, le=180.0)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=20000)] = 5000,
) -> dict:
    _validate_time_window(start, end)
    _validate_latitude_window(min_latitude, max_latitude)
    return service.earthquakes(
        start=start,
        end=end,
        minimum_magnitude=minimum_magnitude,
        min_latitude=min_latitude,
        max_latitude=max_latitude,
        min_longitude=min_longitude,
        max_longitude=max_longitude,
        offset=offset,
        limit=limit,
    )


@router.get("/faults", summary="Read prepared active-fault geometry")
def faults(service: ResearchService) -> dict:
    return service.faults()


@router.get("/faults/{fault_id}", summary="Read one mapped active-fault context record")
def fault(fault_id: str, service: ResearchService) -> dict:
    payload = service.fault(fault_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Research fault was not found.")
    return payload


@router.get("/plate-boundaries", summary="Read prepared plate-boundary geometry")
def plate_boundaries(service: ResearchService) -> dict:
    return service.plate_boundaries()


@router.get(
    "/plate-connections",
    summary="Read prepared event-to-plate-boundary research connections",
)
def plate_connections(service: ResearchService) -> dict:
    return service.plate_connections()


@router.get("/sequences", summary="Read prepared retrospective earthquake sequences")
def sequences(service: ResearchService) -> dict:
    return service.sequences()


@router.get("/sequences/{sequence_id}", summary="Read one prepared retrospective sequence")
def sequence(sequence_id: str, service: ResearchService) -> dict:
    payload = service.sequence(sequence_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Research sequence was not found.")
    return payload


@router.get("/connections", summary="Read prepared event-to-fault research connections")
def connections(service: ResearchService) -> dict:
    return service.connections()


@router.get("/regions/{region_key}", summary="Read one prepared research region")
def region(region_key: str, service: ResearchService) -> dict:
    payload = service.region(region_key)
    if payload is None:
        raise HTTPException(status_code=404, detail="Research region was not found.")
    return payload


def _validate_time_window(start: datetime | None, end: datetime | None) -> None:
    for name, value in (("start", start), ("end", end)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise HTTPException(status_code=422, detail=f"{name} must include a UTC offset.")
    if start is not None and end is not None and start >= end:
        raise HTTPException(status_code=422, detail="start must be earlier than end.")


def _validate_latitude_window(minimum: float | None, maximum: float | None) -> None:
    if minimum is not None and maximum is not None and minimum > maximum:
        raise HTTPException(status_code=422, detail="min_latitude cannot exceed max_latitude.")
