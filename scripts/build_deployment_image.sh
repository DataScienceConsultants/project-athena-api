#!/bin/sh
# Prepare and validate a real catalog before building the deployable image.
set -eu

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 IMAGE_TAG" >&2
    exit 2
fi

# Dockerfile deliberately copies this production path and never copies tests/fixtures.
export ATHENA_DEFAULT_CATALOG_PATH=data/catalog.csv

python -m app.bootstrap_catalog
python -c 'from app.catalog_readiness import validate_catalog_readiness; from app.config import get_settings; newest, count = validate_catalog_readiness(get_settings()); print(f"Validated catalog: {count} events; newest event: {newest.isoformat()}")'
docker build --tag "$1" .
