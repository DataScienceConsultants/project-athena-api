"""Immutable, environment-backed application configuration."""

import os
from dataclasses import dataclass

LOCAL_ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
)


@dataclass(frozen=True, slots=True)
class Settings:
    api_name: str = "Project Athena API"
    api_version: str = "0.1.0"
    athena_version: str = "f21ab8990c4253dbaf708d1f9b511023ee843fec"
    default_region_key: str = "puerto_rico"
    default_catalog_path: str = "data/catalog.csv"
    catalog_freshness_hours: int = 72
    environment_name: str = "development"
    allowed_origins: tuple[str, ...] = LOCAL_ALLOWED_ORIGINS


def _allowed_origins(value: str | None) -> tuple[str, ...]:
    """Parse a comma-separated origin allowlist, ignoring empty entries."""
    if value is None:
        return LOCAL_ALLOWED_ORIGINS
    origins = tuple(
        dict.fromkeys(origin.strip().rstrip("/") for origin in value.split(",") if origin.strip())
    )
    if "*" in origins:
        raise ValueError("ATHENA_ALLOWED_ORIGINS must contain explicit origins, not '*'")
    return origins


def get_settings() -> Settings:
    """Read settings without requiring an environment file."""
    defaults = Settings()

    return Settings(
        api_name=os.getenv("ATHENA_API_NAME", defaults.api_name),
        api_version=os.getenv("ATHENA_API_VERSION", defaults.api_version),
        athena_version=os.getenv("ATHENA_VERSION", defaults.athena_version),
        default_region_key=os.getenv(
            "ATHENA_DEFAULT_REGION_KEY",
            defaults.default_region_key,
        ),
        default_catalog_path=os.getenv(
            "ATHENA_DEFAULT_CATALOG_PATH",
            defaults.default_catalog_path,
        ),
        catalog_freshness_hours=int(
            os.getenv("ATHENA_CATALOG_FRESHNESS_HOURS", defaults.catalog_freshness_hours)
        ),
        environment_name=os.getenv(
            "ATHENA_ENVIRONMENT",
            defaults.environment_name,
        ),
        allowed_origins=_allowed_origins(os.getenv("ATHENA_ALLOWED_ORIGINS")),
    )
