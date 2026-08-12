# Automated production refresh

Project Athena API serves a precomputed Puerto Rico Observatory snapshot. The API intentionally rejects snapshots older than `ATHENA_CATALOG_FRESHNESS_HOURS` (72 hours by default), so production needs a recurring rebuild and deploy process.

`.github/workflows/refresh-production.yml` runs every day at 09:15 UTC (05:15 Puerto Rico time) and can also be started manually. It:

1. downloads and validates the current Puerto Rico catalog with `python -m app.bootstrap_catalog`;
2. validates that the freshly generated Observatory snapshot contains a finite latest anomaly score;
3. authenticates to Google Cloud with GitHub OIDC / Workload Identity Federation;
4. deploys the repository source to the existing Cloud Run service, including the generated `data/catalog.csv` and `data/observatory_report.json` files already re-included by `.gcloudignore`; and
5. requests the deployed `/summary` endpoint and fails unless `latest_anomaly_score` is finite.

The workflow does not weaken the API freshness gate and does not calculate scientific metrics in the browser or during a web request.

## Required GitHub repository configuration

Create these repository **Variables** under Settings → Secrets and variables → Actions → Variables:

- `GCP_PROJECT_ID` — Google Cloud project ID that owns the existing Athena API service.
- `GCP_REGION` — optional; defaults to `us-east1`.
- `GCP_CLOUD_RUN_SERVICE` — optional; defaults to `project-athena-api`.

Create these repository **Secrets** under Settings → Secrets and variables → Actions → Secrets:

- `GCP_WORKLOAD_IDENTITY_PROVIDER` — full Workload Identity Provider resource name, for example `projects/169620809216/locations/global/workloadIdentityPools/github/providers/project-athena-api`.
- `GCP_SERVICE_ACCOUNT` — service account email used by the workflow.

Do not store a long-lived Google service-account JSON key if Workload Identity Federation is available.

## Google Cloud permissions

For source deployment, grant the GitHub deployer identity the permissions required by current Cloud Run source deployment. At minimum this normally includes:

- `roles/run.sourceDeveloper` on the project;
- `roles/serviceusage.serviceUsageConsumer` on the project; and
- `roles/iam.serviceAccountUser` on the Cloud Run service identity.

The Cloud Build service account used by source deployment also needs `roles/run.builder` as documented by Google Cloud.

The Workload Identity Provider should be restricted to this repository (`DataScienceConsultants/project-athena-api`) rather than allowing arbitrary GitHub repositories.

## First activation

After the variables, secrets, Workload Identity Federation, and IAM bindings are configured:

1. open Actions → **Refresh Athena Production**;
2. choose **Run workflow** on `main`;
3. confirm the build, deploy, and production verification steps all pass;
4. open the Project Seismic website and confirm the Observatory anomaly score is populated.

After the first successful manual run, the same process runs automatically every day.

## Failure behavior

The workflow fails before deployment when:

- the catalog or snapshot cannot be generated;
- the fresh snapshot has no finite anomaly score;
- Google Cloud authentication is not configured; or
- deployment fails.

It also fails after deployment if the production `/summary` endpoint does not return a finite `latest_anomaly_score`. This keeps stale or scientifically incomplete snapshots from being silently presented as current.
