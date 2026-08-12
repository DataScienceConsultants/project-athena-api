# Athena research artifact API

The `/research` namespace is a read-only delivery layer for prepared Project Athena research
artifacts. It does not calculate anomaly scores, infer faults, identify sequences, or perform other
scientific analysis during an HTTP request.

The default bundle directory is `data/global_research/global-m6-1976-2025`. Override it with
`ATHENA_RESEARCH_BUNDLE_PATH` in deployments where the prepared bundle is mounted elsewhere.

## Required artifacts

- `metadata.json` — cohort provenance and research configuration.
- `catalog.csv` — normalized historical earthquake catalog.

## Optional artifacts

- `fault_associations.csv` — precomputed event-to-nearest-mapped-fault geographic context.
- `faults.geojson` — prepared active-fault geometry for map display.
- `plate_boundaries.geojson` — prepared plate-boundary geometry for map display.
- `sequences.json` — precomputed retrospective sequence records.

Missing optional artifacts are returned as explicitly unavailable rather than replaced with fixture or
invented scientific data. Missing required artifacts return HTTP 503.

## Project Seismic contract

The namespace matches the Athena Research Console adapter in Project Seismic:

- `GET /research/global/summary`
- `GET /research/earthquakes`
- `GET /research/faults`
- `GET /research/faults/{fault_id}`
- `GET /research/plate-boundaries`
- `GET /research/sequences`
- `GET /research/sequences/{sequence_id}`
- `GET /research/connections`
- `GET /research/regions/{region_key}`

`/research/earthquakes` supports magnitude, UTC time, geographic bounds, offset, and limit filters.
Longitude bounds may cross the international date line by supplying a minimum longitude greater than
the maximum longitude.

All responses remain retrospective and nonpredictive. A nearest mapped active-fault association is
geographic context, not causal attribution, and the absence of mapped fault geometry must not be
interpreted as the absence of active faulting.
