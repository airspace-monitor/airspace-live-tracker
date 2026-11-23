#!/bin/bash
# Collector key admin on k3s (docs/04-pipelines.md, M1.7). Runs `python -m ingest.admin` in a
# throwaway pod with the owner role, as the `ingest-admin` compose service does locally. The pod
# runs to completion and its logs are read afterwards: attaching with `kubectl run -i` can miss
# the output of a pod that finishes in under a second.
# Example: infra/ingest-admin.sh add-collector --id pi-02 --owner daniel
set -euo pipefail

NS=airspace
name=ingest-admin-$(date +%s)
image=$(kubectl -n "$NS" get deploy ingest-api -o jsonpath='{.spec.template.spec.containers[0].image}')
args=$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1:]))' "$@")
overrides=$(cat <<EOF
{"spec": {"restartPolicy": "Never", "containers": [{
  "name": "$name", "image": "$image", "imagePullPolicy": "Never",
  "command": ["python", "-m", "ingest.admin"], "args": $args,
  "env": [
    {"name": "AIRSPACE_OWNER_PASSWORD", "valueFrom": {"secretKeyRef": {"name": "airspace-env", "key": "AIRSPACE_OWNER_PASSWORD"}}},
    {"name": "ADMIN_DATABASE_URL", "value": "postgres://airspace_owner:\$(AIRSPACE_OWNER_PASSWORD)@db:5432/airspace?sslmode=disable"}
  ]}]}}
EOF
)
trap 'kubectl -n "$NS" delete pod "$name" --ignore-not-found --wait=false >/dev/null' EXIT
kubectl -n "$NS" run "$name" --restart=Never --image="$image" --overrides="$overrides" >/dev/null

phase=Pending
for _ in $(seq 120); do
  phase=$(kubectl -n "$NS" get pod "$name" -o jsonpath='{.status.phase}')
  case $phase in Succeeded|Failed) break ;; esac
  sleep 1
done
if [ "$phase" != Succeeded ]; then
  echo "ingest-admin pod ended as $phase:" >&2
  kubectl -n "$NS" logs "$name" >&2 || true
  exit 1
fi
kubectl -n "$NS" logs "$name"
