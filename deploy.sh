#!/usr/bin/env bash
#
# Deploy to Cloud Run.
#
# Credentials go into Secret Manager, never into --set-env-vars: env vars set
# on the command line land in your shell history and in the Cloud Run service
# description, where anyone with viewer access can read them. li_at is a
# complete account credential, so that matters.
#
#   ./deploy.sh                 deploy using values from .env
#   REGION=europe-west1 ./deploy.sh
#
set -euo pipefail

SERVICE="${SERVICE:-lin-scrapper}"
REGION="${REGION:-us-central1}"
PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"

if [[ -z "${PROJECT}" || "${PROJECT}" == "(unset)" ]]; then
  echo "No GCP project set. Run: gcloud config set project <project-id>" >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "No .env found. Copy .env.example and fill it in first." >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a; source .env; set +a

for var in LI_COOKIE_HEADER API_KEY; do
  if [[ -z "${!var:-}" ]]; then
    echo "${var} is empty in .env" >&2
    exit 1
  fi
done

echo "Project ${PROJECT}, region ${REGION}, service ${SERVICE}"

gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com \
  --project "${PROJECT}"

# Each deploy adds a new secret version, so rotating a cookie is just a re-run.
sync_secret() {
  local name="$1" value="$2"
  if ! gcloud secrets describe "${name}" --project "${PROJECT}" &>/dev/null; then
    gcloud secrets create "${name}" --replication-policy=automatic \
      --project "${PROJECT}"
  fi
  printf '%s' "${value}" | gcloud secrets versions add "${name}" \
    --data-file=- --project "${PROJECT}"
}

sync_secret lin-scrapper-cookie-header "${LI_COOKIE_HEADER}"
sync_secret lin-scrapper-api-key "${API_KEY}"

# Grant the runtime service account read access to the three secrets.
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT}" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for name in lin-scrapper-cookie-header lin-scrapper-api-key; do
  gcloud secrets add-iam-policy-binding "${name}" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role=roles/secretmanager.secretAccessor \
    --project "${PROJECT}" >/dev/null
done

# --allow-unauthenticated makes the URL public; the app's own X-API-Key is
# what actually gates it.
gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --project "${PROJECT}" \
  --allow-unauthenticated \
  --set-secrets "LI_COOKIE_HEADER=lin-scrapper-cookie-header:latest,API_KEY=lin-scrapper-api-key:latest"

URL="$(gcloud run services describe "${SERVICE}" --region "${REGION}" \
  --project "${PROJECT}" --format='value(status.url)')"

echo
echo "Deployed: ${URL}"
echo
echo "Verify:"
echo "  curl ${URL}/health"
echo "  curl -X POST ${URL}/api/integrations/linkedin/profile \\"
echo "    -H 'Content-Type: application/json' -H \"X-API-Key: \${API_KEY}\" \\"
echo "    -d '{\"url\":\"https://www.linkedin.com/in/<slug>\"}'"
