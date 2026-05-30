#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-profbailey}"
ARCHIVE_BUCKET="${ARCHIVE_BUCKET:-profbailey-archive-assets}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Applying Cloud Storage policy for ${PROJECT_ID}"

gcloud storage buckets update "gs://${ARCHIVE_BUCKET}" \
  --project="${PROJECT_ID}" \
  --lifecycle-file="${ROOT_DIR}/infra/archive-assets.lifecycle.json"

gcloud storage objects update "gs://${ARCHIVE_BUCKET}/**" \
  --cache-control='public,max-age=31536000,immutable'

if [[ "${PRIVATE_STORAGE:-0}" == "1" ]]; then
  gcloud storage buckets remove-iam-policy-binding "gs://${ARCHIVE_BUCKET}" \
    --member=allUsers \
    --role=roles/storage.objectViewer \
    --quiet || true
  gcloud storage buckets update "gs://${ARCHIVE_BUCKET}" --public-access-prevention --project="${PROJECT_ID}"
else
  gcloud storage buckets update "gs://${ARCHIVE_BUCKET}" \
    --no-public-access-prevention \
    --project="${PROJECT_ID}"
  gcloud storage buckets add-iam-policy-binding "gs://${ARCHIVE_BUCKET}" \
    --member=allUsers \
    --role=roles/storage.objectViewer \
    --quiet >/dev/null
fi

echo "Cloud Storage policy applied."
