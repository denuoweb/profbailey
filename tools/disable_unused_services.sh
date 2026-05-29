#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-profbailey}"

unused_services=(
  analyticshub.googleapis.com
  appengine.googleapis.com
  bigqueryconnection.googleapis.com
  bigquerydatapolicy.googleapis.com
  bigquerydatatransfer.googleapis.com
  bigquerymigration.googleapis.com
  bigqueryreservation.googleapis.com
  bigquerystorage.googleapis.com
  dataform.googleapis.com
  dataplex.googleapis.com
  fcm.googleapis.com
  firebaseinstallations.googleapis.com
  firebaseremoteconfigrealtime.googleapis.com
  firebaseremoteconfig.googleapis.com
  identitytoolkit.googleapis.com
  pubsub.googleapis.com
  runtimeconfig.googleapis.com
  securetoken.googleapis.com
  telemetry.googleapis.com
  testing.googleapis.com
)

protected_services=(
  bigquery.googleapis.com
  cloudtrace.googleapis.com
  datastore.googleapis.com
  sql-component.googleapis.com
)

echo "Checking for resources before disabling unused APIs in ${PROJECT_ID}"

if bq ls --project_id="${PROJECT_ID}" | sed '1,2d' | rg -q '\S'; then
  echo "BigQuery datasets exist; aborting."
  exit 1
fi

if gcloud pubsub topics list --project="${PROJECT_ID}" --format='value(name)' | rg -q '\S'; then
  echo "Pub/Sub topics exist; aborting."
  exit 1
fi

if gcloud pubsub subscriptions list --project="${PROJECT_ID}" --format='value(name)' | rg -q '\S'; then
  echo "Pub/Sub subscriptions exist; aborting."
  exit 1
fi

if firebase apps:list --project "${PROJECT_ID}" | rg -q 'App ID'; then
  echo "Firebase apps exist; aborting."
  exit 1
fi

for service in "${unused_services[@]}"; do
  if gcloud services list --enabled --project="${PROJECT_ID}" --format='value(config.name)' | rg -Fxq "${service}"; then
    echo "Disabling ${service}"
    if ! gcloud services disable "${service}" --project="${PROJECT_ID}" --quiet; then
      echo "Skipped ${service}; Service Usage reported an active dependency."
    fi
  fi
done

echo "Not forcing services with active cloudapis.googleapis.com dependencies:"
printf '  %s\n' "${protected_services[@]}"

echo "Remaining enabled APIs:"
gcloud services list --enabled --project="${PROJECT_ID}" --format='value(config.name)' | sort
