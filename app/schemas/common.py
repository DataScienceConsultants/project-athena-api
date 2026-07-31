"""Response models owned by the delivery layer."""

from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class VersionResponse(BaseModel):
    api_version: str
    athena_version: str
    python_version: str


class StatusResponse(BaseModel):
    region_key: str
    region_name: str
    overall_status: str
    catalog_as_of_utc: str
    source_event_count: int
    latest_anomaly_score: float | None
    latest_anomaly_level: str | None
    trend_direction: str
    trend_strength: str
    report_is_nonpredictive: bool


class SummaryResponse(BaseModel):
    """Stable, frontend-oriented view of Athena's serialized report."""

    region_key: str
    region_name: str
    overall_status: str
    catalog_as_of_utc: str
    source_event_count: int
    latest_anomaly_score: float | None
    latest_anomaly_level: str | None
    trend_direction: str
    trend_strength: str
    swarm_count: int | None
    executive_summary: str
    disclaimer: str
    report_is_nonpredictive: bool


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class DiscoveryResponse(BaseModel):
    service: str
    version: str
    endpoints: dict[str, Any]
