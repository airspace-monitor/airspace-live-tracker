#!/bin/bash
# Collector key admin on k3s (docs/04-pipelines.md, M1.7). Runs `python -m ingest.admin` in a
# throwaway pod with the owner role, as the `ingest-admin` compose service does locally. The
# container is named like the pod, so the override replaces kubectl's generated container.
# Example: infra/ingest-admin.sh add-collector --id pi-02 --owner daniel
set -euo pipefail

name=ingest-admin-$(date +%s)
image=$(kubectl -n airspace get deploy ingest-api -o jsonpath='{.spec.template.spec.containers[0].image}')
overrides=$(cat <<EOF
{"spec": {"restartPolicy": "Never", "containers": [{
  "name": "$name", "image": "$image", "imagePullPolicy": "Never", "stdin": true,
  "command": ["python", "-m", "ingest.admin"], "args": $(python3 -c 'import json, sys; print(json.dumps(sys.argv[1:]))' "$@"),
  "env": [
    {"name": "AIRSPACE_OWNER_PASSWORD", "valueFrom": {"secretKeyRef": {"name": "airspace-env", "key": "AIRSPACE_OWNER_PASSWORD"}}},
    {"name": "ADMIN_DATABASE_URL", "value": "postgres://airspace_owner:\$(AIRSPACE_OWNER_PASSWORD)@db:5432/airspace?sslmode=disable"}
  ]}]}}
EOF
)
kubectl -n airspace run "$name" --rm -i --quiet --restart=Never \
  --image="$image" --overrides="$overrides"
