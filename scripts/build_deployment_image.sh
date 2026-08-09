#!/bin/sh
# Prepare and validate a matched catalog/report pair before building the image.
set -eu

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 IMAGE_TAG" >&2
    exit 2
fi

# Dockerfile deliberately copies this production path and never copies tests/fixtures.
export ATHENA_DEFAULT_CATALOG_PATH=data/catalog.csv
export ATHENA_REPORT_SNAPSHOT_PATH=data/observatory_report.json

python -m app.bootstrap_catalog
python -c 'from app.services.athena import AthenaService; report = AthenaService().build_report().to_dict(); print(f"Validated report snapshot: {len(report)} top-level fields")'
docker build --tag "$1" .
