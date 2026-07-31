# Project Athena API

Project Athena API 0.1.0 is a thin, deterministic FastAPI service over the existing
[Project Athena](https://github.com/DataScienceConsultants/project-athena) analytics engine. It is
only a service and delivery layer: it neither copies nor recalculates Athena's scientific logic.

## Architecture

HTTP routers depend on a focused `AthenaService`, which invokes Athena's public unified Observatory
intelligence builder once per request. API-owned payloads use Pydantic; the full Observatory report
and its time-series section pass through Athena's `to_dict()` serialization unchanged. There is no
database, authentication, background processing, scheduler, or frontend.

Project Athena is the historical seismic analytics engine. Project Athena API delivers those results
over HTTP. Project Seismic is a separate, broader project and is not implemented by this service.

## Install and run

Python 3.12 is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
uvicorn app.main:app --reload
```

Athena is installed directly from its GitHub repository at commit
`d15bc49e1deb2e4730d7df03210300a7fce7e107`; the exact immutable pin is recorded in
`pyproject.toml` because no release tag was available when version 0.1.0 was prepared. Athena source
is not vendored here.

> **Integration note:** version 0.1.0 expects Athena to expose
> `src.observatory.build_observatory_intelligence_report`, accepting `region_key` and
> `catalog_path`, and returning an object with `to_dict()`. Any upstream incompatibility must be
> resolved in Athena rather than by copying or reimplementing its internals here.

## Configuration

All settings have local defaults and may be overridden independently:

| Variable | Default |
| --- | --- |
| `ATHENA_API_NAME` | `Project Athena API` |
| `ATHENA_API_VERSION` | `0.1.0` |
| `ATHENA_VERSION` | pinned commit shown above |
| `ATHENA_DEFAULT_REGION_KEY` | `puerto_rico` |
| `ATHENA_DEFAULT_CATALOG_PATH` | `data/catalog.csv` |
| `ATHENA_ENVIRONMENT` | `development` |

## Endpoints

- `GET /health` — lightweight service health; never runs Athena.
- `GET /version` — API, Athena, and Python runtime versions.
- `GET /status` — concise status derived from the unified report.
- `GET /summary` — stable, frontend-ready historical summary for Project Seismic's MVP.
- `GET /observatory` — Athena's complete serialized unified report.
- `GET /timeseries` — only the unified report's serialized `time_series` section.
- `GET /` — service discovery.

Example:

```bash
curl http://127.0.0.1:8000/status
curl http://127.0.0.1:8000/summary
curl http://127.0.0.1:8000/observatory
```

If the configured catalog/report is unavailable, analytical endpoints return HTTP 503 with a stable,
safe JSON error. OpenAPI documentation is available at `/docs`.

## Quality checks

```bash
ruff check .
git diff --check
python -m compileall -q app
pytest -q
```

Tests inject deterministic reports and never access live USGS services or production catalogs.

## Nonpredictive disclaimer

Results describe historical seismic observations and are **nonpredictive**. This service does not
predict earthquakes and does not estimate future earthquake probability. It does not generate
alerts and does not replace official earthquake, tsunami, emergency-management, or public-safety
information. Consult the responsible government authorities for current official information.
