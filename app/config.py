"""Immutable, environment-backed application configuration."""

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    api_name: str = "Project Athena API"
    api_version: str = "0.1.0"
    athena_version: str = "f21ab8990c4253dbaf708d1f9b511023ee843fec"
    default_region_key: str = "puerto_rico"
    default_catalog_path: str = "data/catalog.csv"
    environment_name: str = "development"


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
        environment_name=os.getenv(
            "ATHENA_ENVIRONMENT",
            defaults.environment_name,
        ),
    )