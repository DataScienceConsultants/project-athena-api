# Project Athena API

Project Athena API 0.1.0 is a thin, deterministic FastAPI service over the existing
[Project Athena](https://github.com/DataScienceConsultants/project-athena) analytics engine. It is
only a service and delivery layer: it neither copies nor recalculates Athena's scientific logic.

## Architecture

HTTP routers depend on a focused `AthenaService`, which reads a validated, precomputed unified
Observatory report from disk. API-owned payloads use Pydantic; the full Observatory report
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
python -m app
# For auto-reload during local development instead:
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
```

Athena is installed directly from its GitHub repository at commit
`89166e33128aac5b1eae9c3f2e161441bd9ca744`; the exact immutable pin is recorded in
`pyproject.toml` because no release tag was available when version 0.1.0 was prepared. Athena source
is not vendored here.

> **Integration note:** version 0.1.0 expects Athena to expose
> `src.observatory.build_observatory_intelligence_report`, accepting `region_key` and
> `catalog_path`, and returning an object with `to_dict()`. Any upstream incompatibility must be
> resolved in Athena rather than by copying or reimplementing its internals here.

## Deployment

The repository includes a minimal Python 3.12 container. It installs the immutable Athena pin and
starts Uvicorn directly (without a development reloader), binds every container interface, honors
the platform `PORT`, and trusts forwarded proxy headers:

```bash
docker build -t project-athena-api .
docker run --rm -p 8000:8000 \
  -e ATHENA_ALLOWED_ORIGINS=https://datascienceconsultants.github.io \
  project-athena-api
```

The production start command, whether or not a container is used, is:

```bash
PORT=8000 python -m app
```

### Runtime catalog strategy

No production catalog is checked into source control. The old generated sample is only
`tests/fixtures/catalog.csv` and is never a production default or copied into the image. Prepare a
real catalog and its matching report snapshot as a one-time operation (and whenever refreshing
either) with the canonical preparation command:

```bash
python -m app.bootstrap_catalog
```

It resolves the configured Puerto Rico bounds, downloads through Athena's public catalog API, lets
Athena validate and deduplicate the events, builds Athena's public unified report, and writes strict
JSON to `ATHENA_REPORT_SNAPSHOT_PATH`. Both candidates must succeed before the matched catalog and
snapshot are promoted. Promotion is catalog-first with deterministic rollback; metadata validation
also prevents an interrupted promotion from serving mixed versions. A failed download or report
build exits nonzero and preserves both existing production files. It never falls back to fixture
data. **Never delete either prepared file before refreshing it.** The default rolling
10-year interval is downloaded in consecutive one-year chunks to stay below upstream result limits.
Each chunk may be empty, and boundary duplicates are resolved by Athena before one chronological CSV
is atomically promoted. The command logs every requested UTC chunk and its event count.

The interval and chunk width can be overridden. For example, to retain the previous rolling one-year
bootstrap behavior:

```bash
ATHENA_BOOTSTRAP_LOOKBACK_DAYS=365 python -m app.bootstrap_catalog
```

Set `ATHENA_BOOTSTRAP_START_UTC` and `ATHENA_BOOTSTRAP_END_UTC` to ISO-8601 timestamps with UTC
offsets for a fixed interval. An explicit start takes precedence over the rolling lookback.

The standalone `python -m app.build_report_snapshot` command can rebuild a snapshot from an already
configured catalog, but `python -m app.bootstrap_catalog` is canonical for production because it
safely prepares and promotes the pair.

Preparation is deliberately **not** part of web startup: Cloud Run may autoscale many instances, and
each instance must start from the same prepared snapshot rather than perform a full external USGS
download. The web command only starts the API. It validates readiness before analytical requests and
returns a safe 503 for missing, malformed, stale, or mismatched snapshot/catalog data; it never
downloads data or performs Athena's expensive full report build. The container also installs
`config/regions.json` alongside Athena as a compatibility measure for Athena 0.4.1, whose wheel does
not include that package data.

The MVP deployment workflow prepares a real snapshot before `docker build`, validates freshness,
and includes `data/catalog.csv` and `data/observatory_report.json` in the image. The helper stops
immediately if preparation or validation
fails, so Docker cannot accidentally build with an absent, stale, empty, or synthetic catalog:

```bash
./scripts/build_deployment_image.sh \
  REGION-docker.pkg.dev/PROJECT/REPOSITORY/project-athena-api:$(git rev-parse --short HEAD)
```

Both generated files are ignored by Git and remain build inputs only. Do not replace the catalog
with `tests/fixtures/catalog.csv`. Docker's `COPY data ./data` includes the prepared pair in every
image. The checked-in `.gcloudignore` explicitly re-includes both ignored deployment inputs for
Cloud Build source uploads; ensure any global override retains those exceptions.

For Cloud Run, authenticate Docker, run the helper, push that successfully validated image, then
deploy it while explicitly configuring the production origin and freshness policy:

```bash
IMAGE=REGION-docker.pkg.dev/PROJECT/REPOSITORY/project-athena-api:$(git rev-parse --short HEAD)
./scripts/build_deployment_image.sh "$IMAGE"
docker push "$IMAGE"
gcloud run deploy project-athena-api \
  --image "$IMAGE" \
  --region REGION \
  --set-env-vars ATHENA_ALLOWED_ORIGINS=https://datascienceconsultants.github.io,ATHENA_CATALOG_FRESHNESS_HOURS=72
```

To refresh, rerun the helper with a new immutable image tag, push it, and deploy a new Cloud Run
revision. All autoscaled instances of that revision then use the identical prepared snapshot. Do not
refresh by restarting the API or calling an analytical endpoint.

For a future long-lived architecture, run the bootstrap as a dedicated **Cloud Run Job** triggered by
**Cloud Scheduler**, publish the atomic catalog to versioned **Cloud Storage**, and promote a
validated object for API revisions to consume. That separates scheduled ingestion from serving
without making instance startup dependent on USGS availability.

## Configuration

All settings have local defaults and may be overridden independently:

| Variable | Default |
| --- | --- |
| `ATHENA_API_NAME` | `Project Athena API` |
| `ATHENA_API_VERSION` | `0.1.0` |
| `ATHENA_VERSION` | pinned commit shown above |
| `ATHENA_DEFAULT_REGION_KEY` | `puerto_rico` |
| `ATHENA_DEFAULT_CATALOG_PATH` | `data/catalog.csv` |
| `ATHENA_REPORT_SNAPSHOT_PATH` | `data/observatory_report.json` |
| `ATHENA_BOOTSTRAP_LOOKBACK_DAYS` | `3650` (rolling 10 years) |
| `ATHENA_BOOTSTRAP_CHUNK_DAYS` | `365` |
| `ATHENA_BOOTSTRAP_START_UTC` | unset; overrides lookback when set |
| `ATHENA_BOOTSTRAP_END_UTC` | current UTC time |
| `ATHENA_CATALOG_FRESHNESS_HOURS` | `72` |
| `ATHENA_ENVIRONMENT` | `development` |
| `ATHENA_ALLOWED_ORIGINS` | local origins on ports `3000` and `5173` |
| `PORT` | `8000` |

### CORS

`ATHENA_ALLOWED_ORIGINS` is a comma-separated exact allowlist. Localhost and `127.0.0.1` origins on
ports 3000 and 5173 are allowed only when the variable is unset. Production should explicitly set:

```bash
ATHENA_ALLOWED_ORIGINS=https://datascienceconsultants.github.io
```

Add multiple origins with commas. Do not configure `*`: credentialed CORS requires explicit origins.
An explicitly empty value disables cross-origin access.

## Athena Research Runner

`python -m app.research` creates historical, descriptive research benchmarks without changing the
Puerto Rico production API, `data/catalog.csv`, or `data/observatory_report.json`. It uses Athena's
existing catalog normalization, deduplication, Observatory report builder, and daily anomaly time
series; it does not introduce or modify scoring. All four artifacts (`catalog.csv`,
`observatory_report.json`, `timeseries.json`, and `metadata.json`) are built in a temporary sibling
directory and promoted together only after the complete run succeeds.

Regions are selected from `config/regions.json`. The first additional benchmark is `venezuela`,
named **Venezuela and northeastern Caribbean seismic region**. Its 7–14° N, 68–59° W research box
was deliberately selected to include northeastern Venezuela, the adjacent Caribbean seismic
setting, and surrounding activity relevant to the 21 August 2018 M7.3 event. It is a seismic-study
window, **not** a representation of Venezuela's political boundaries. Its explicit default USGS
minimum magnitude remains 1.0; a long interval at that threshold can involve substantial download
and processing time. Use `--minimum-magnitude` when an intentional benchmark requires another
threshold—the runner never silently raises it.

The `colombia` benchmark is named **Colombia and adjacent seismic region**. Its bounds are
5° S–14° N and 82–66° W, with a default USGS minimum magnitude of 2.5. This deliberately bounded
seismic-study window covers Colombia, the offshore Pacific subduction margin, and adjacent
Caribbean and Andean seismic settings relevant to the 10 August 2026 earthquake; it is **not** an
exact political boundary or a general South America bounding box. The benchmark uses the frozen,
existing Athena catalog, Observatory, anomaly-scoring, and time-series methodology for
out-of-sample retrospective analysis of observed seismic behavior. It does not claim prediction or
forecasting capability.

Run the Colombia benchmark (writing only to `data/research/colombia/`) with:

```bash
python -m app.research \
  --region colombia \
  --start 2021-01-01 \
  --end 2026-08-11
```

Dates are UTC calendar boundaries and form the half-open interval `[start, end)`. Thus this example
includes all of 2016 through 2020 and writes to `data/research/venezuela/`:

```bash
python -m app.research \
  --region venezuela \
  --start 2016-01-01 \
  --end 2021-01-01
```

Use `--output data/research/another-benchmark` for a custom isolated directory,
`--minimum-magnitude 2.0` for an explicit threshold override, or `--chunk-days 180` to reduce the
default 365-day USGS request chunks. Run `python -m app.research --help` for all options. Generated
research data is ignored by Git (apart from `data/research/.gitkeep`) and remains separate from the
production Puerto Rico catalog and report snapshot.

These artifacts characterize historical seismic activity, observed anomaly behavior, and historical
comparison only. They retain Athena's existing nonpredictive framing and are not operational alerts.
Metadata records the requested range, configured bounds and minimum magnitude, total event count,
and the available and unavailable time-series period counts supplied by the existing report.

## Athena Historical Benchmark Runner

The research-only benchmark runner measures how the **existing frozen Athena model** behaved around
curated historical earthquakes. It reads the unmodified artifacts produced by `app.research`; it
does not alter scoring, weights, thresholds, baselines, Observatory or daily time-series
calculations, region definitions, or production API paths. Benchmark entries in
`config/benchmarks.json` contain only observed event metadata and artifact coverage dates—never an
expected score or a success/failure label.

First generate the configured region artifact if it is absent (the benchmark command prints the
exact required research command), then run one event or the full set:

```bash
python -m app.benchmark --benchmark colombia_2026_08_10
python -m app.benchmark --all
python -m app.benchmark --all --output data/benchmarks
```

Each event produces `data/benchmarks/<benchmark_id>/result.json`, containing separate event-day and
7-, 14-, and 30-day pre-event measurements, persistence and recency measurements, regional base
rates, retrospective future-event associations, and catalog adequacy. `--all` additionally writes
`summary.json` and one-row-per-event `summary.csv`. Null source values remain unavailable rather
than becoming zero, and the earthquake day is excluded from every pre-event window.

Catalog adequacy uses the artifact's available/candidate period percentage: **usable** is at least
90%, **limited** is at least 50% but below 90%, and **insufficient** is below 50% (including no
candidate periods). Regime labels are deterministic reporting helpers based on the prior 14 days:
**quiet** has no score ≥70 day; **isolated_anomaly** has one; **intermittent_anomalies** has two or
more but no three-day run; and **persistent_anomalous_regime** has a run of at least three.

Future-event fields report only retrospective associations between anomaly days and later daily
maximum magnitudes. Regional results always use the fixed, directly comparable M5+, M6+, and M7+
cutoffs. A separately named benchmark-magnitude section retains the event-specific cutoff and does
not replace those fixed regional statistics. Every horizon begins on the day after an anomaly day.
These measurements are not probabilities, forecasts, risks, or operational alerts. **Athena
benchmark analysis describes historical associations and does not establish earthquake prediction
capability.**

## Athena Control-Window Validation

The benchmark runner treats the curated earthquakes as **cases** and deterministically samples
ordinary comparison **control windows** from the same region's existing research time series.
Selection is independent of Athena anomaly score: an eligible anchor needs all 30 preceding UTC
days of artifact coverage and must not be within 30 days before or after (inclusive) a day whose
`maximum_magnitude` is M7.0 or greater. No network data is fetched.

Cases and controls use the same shared 30-, 14-, and 7-day feature calculations, always excluding
the anchor day. Outputs report descriptive empirical percentile ranks, fractions of controls at or
above the case, recency null counts, and regime distributions. These retrospective comparisons are
not p-values, probabilities, forecasts, or claims of predictive performance; Athena scoring remains
frozen.

Sampling is reproducible with `--seed` (default `42`) and requests 100 controls per benchmark by
default. Controls may overlap. Pass `--non-overlapping-controls` to require their anchor dates to be
at least 30 days apart; the output clearly reports when fewer eligible controls exist than requested.
Catalogs marked limited are retained and labeled, while insufficient catalogs are rejected.

```bash
python -m app.benchmark \
  --benchmark puerto_rico_2020_01_07 \
  --controls-per-benchmark 100 \
  --seed 42

python -m app.benchmark \
  --all \
  --controls-per-benchmark 100 \
  --seed 42
```

Each case writes `controls.json` beside `result.json`. Full runs also write JSON and CSV summary and
validation-summary files with one row per earthquake case. The compact control output contains only
anchor features, not a duplicate of the underlying regional time series.

## Endpoints

- `GET /health` — lightweight service health; never runs Athena.
- `GET /version` — API, Athena, and Python runtime versions.
- `GET /status` — concise status derived from the unified report.
- `GET /summary` — stable, frontend-ready historical summary for Project Seismic's MVP.
- `GET /observatory` — Athena's complete serialized unified report.
- `GET /timeseries` — only the unified report's serialized `time_series` section.
- `GET /timeseries/chart` — compact daily chart data projected from Athena anomaly results. An
  optional positive `days` query parameter returns the most recent N available points.
- `GET /` — service discovery.

Analytical endpoints validate that the catalog exists, is readable, and has at least one event. The
snapshot metadata's `generated_at_utc` is the operational freshness signal and must be no older than
`ATHENA_CATALOG_FRESHNESS_HOURS`. In contrast, `catalog_as_of_utc` is scientific metadata: it records
the newest earthquake observation in the catalog and is not itself a freshness gate. A recently
generated snapshot can therefore remain ready during a quiet seismic period even when its newest
event is days or weeks old.

The snapshot region, event count, `catalog_as_of_utc`, report structure, and file age must also agree
with the catalog and configuration. Missing, empty, malformed, stale, or mismatched inputs get the
same safe HTTP 503 response; `/health` and `/version` remain lightweight and do not read either file.
Repeated analytical requests deserialize the cached report and never invoke Athena's scientific
builder.

Deployment smoke tests (the first three should return HTTP 200):

```bash
BASE_URL=http://127.0.0.1:8000
curl --fail --show-error "$BASE_URL/health"
curl --fail --show-error "$BASE_URL/version"
curl --fail --show-error "$BASE_URL/summary"
curl --fail --show-error "$BASE_URL/observatory"
curl --fail --show-error "$BASE_URL/timeseries"
curl --fail --show-error "$BASE_URL/timeseries/chart?days=30"
```

Measure a warm chart request (under one second is ideal; under two is acceptable, and under three
remains usable):

```bash
SERVICE_URL=http://127.0.0.1:8000
curl -s -o /dev/null \
  -w "HTTP: %{http_code}\nTotal: %{time_total}s\nTTFB: %{time_starttransfer}s\nSize: %{size_download} bytes\n" \
  "$SERVICE_URL/timeseries/chart?days=30"
```

After intentionally pointing `ATHENA_DEFAULT_CATALOG_PATH` at a missing file and restarting, verify
that liveness stays 200 while analytics safely return 503:

```bash
curl --fail --show-error "$BASE_URL/health"
test "$(curl --silent --output /dev/null --write-out '%{http_code}' "$BASE_URL/summary")" = 503
```

Example:

```bash
curl http://127.0.0.1:8000/status
curl http://127.0.0.1:8000/summary
curl http://127.0.0.1:8000/observatory
```

Frontend clients can request all available history or bound the response for a chart without
changing or aggregating Athena's observations:

```javascript
const response = await fetch(`${apiBase}/timeseries/chart?days=90`);
if (!response.ok) throw new Error(`Chart request failed: ${response.status}`);
const { analysis_start, analysis_end, frequency, points } = await response.json();

// points are oldest-to-newest and contain only date, anomaly_score, anomaly_level,
// event_count, maximum_magnitude, total_energy_joules, and mean_depth_km.
renderChart({ analysis_start, analysis_end, frequency, points });
```

Omit `days` for the complete available history (for example, `GET /timeseries/chart`). Values for
unavailable metrics are JSON `null`; they are never replaced with zero. Invalid values such as
`days=0` or `days=-1` receive FastAPI's standard HTTP 422 validation response.

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

## Athena Seismic Sequence Analysis

The research-only sequence runner adds a descriptive, retrospective layer above frozen Athena
research artifacts. It does not alter anomaly scoring or production behavior. Magnitudes use the
standardized research terms **strong** for M6.0–6.9, **major** for M7.0–7.9, and **great** for M8.0
and above; the sequence trigger is M6.0+, so all three classes qualify.

A sequence requests context from 365 days before its first qualifying event through 365 days after
its last qualifying event. Each additional M6+ event within the current window recursively extends
the endpoint to 365 days after that event. Boundaries are never selected from anomaly scores.
If the artifact lacks the full prehistory, the sequence is left-censored. If it ends before a quiet
post-event year can be observed, the sequence remains open and is marked
`ongoing_or_right_censored`; absent future observations are not treated as quiet days.

Generate output under `data/sequences/<region_key>` without network access:

```bash
python -m app.sequences --region puerto_rico
python -m app.sequences --region colombia
python -m app.sequences --all
```

The source `data/research/<region_key>/catalog.csv` and `timeseries.json` must already exist. The
runner reports event context, deterministic pre/between/post windows, and monthly pre-event
trajectories. These measurements do not assign predictive phases or make forecasts. **Observed
temporal association does not establish that an earlier earthquake caused, predicted, or served as
a precursor to a later earthquake.**
