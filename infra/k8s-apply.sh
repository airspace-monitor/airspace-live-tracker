#!/bin/bash
# Builds our images, imports them into k3s, syncs the secret, runs migrations, then applies the
# manifests and waits for the rollout (docs/adr/0005-single-node-k3s.md). Used by deploy.sh on the
# VM and by CI's k8s job on a throwaway k3s. Safe to run again.
# Usage: infra/k8s-apply.sh [env-file]   (default infra/.env)
set -euo pipefail

NS=airspace
IMAGES=(airspace-ingest airspace-api airspace-stream airspace-orchestrator)
# Local volume directories and the user each image runs as (infra/k8s/storage.yaml).
VOLUMES=("db-data 1000" "dagster-storage 10002" "grafana-data 472")

main() {
  cd "$(dirname "$0")/.."
  local env_file=${1:-infra/.env}
  command -v k3s >/dev/null || { echo "k3s is not installed: run infra/k3s-install.sh first" >&2; exit 1; }

  build_and_import "$env_file"
  write_overlay
  ensure_volumes

  # Namespace, secret and migrations first: everything else references them.
  kubectl apply -f infra/k8s/namespace.yaml
  kubectl -n "$NS" create secret generic airspace-env --from-env-file="$env_file" \
    --dry-run=client -o yaml | kubectl apply -f -
  kubectl -n "$NS" create configmap airspace-migrations --from-file=db/migrations \
    --dry-run=client -o yaml | kubectl apply -f -

  # The database and its storage before migrations, migrations before the new code
  # (docs/09-conventions.md#migrations).
  kubectl apply -k infra/.deploy -l 'app in (db,storage)'
  kubectl -n "$NS" rollout status statefulset/db --timeout=10m
  kubectl -n "$NS" wait --for=condition=Ready pod/db-0 --timeout=10m
  kubectl -n "$NS" delete job migrate --ignore-not-found --wait=true
  kubectl apply -f infra/k8s/jobs/migrate.yaml
  if ! kubectl -n "$NS" wait --for=condition=complete job/migrate --timeout=5m; then
    kubectl -n "$NS" logs job/migrate >&2 || true
    echo "migrations failed; the running code is unchanged" >&2
    exit 1
  fi

  kubectl apply -k infra/.deploy
  for d in $(kubectl -n "$NS" get deploy -o name); do
    kubectl -n "$NS" rollout status "$d" --timeout=10m
  done
  kubectl -n "$NS" get pods -o wide
}

# Build with the compose definitions (same Dockerfiles as CI), then tag each image by its ID: an
# unchanged image keeps its tag, so its pods are not restarted.
build_and_import() {
  (cd infra && docker compose --env-file "../$1" build --quiet)
  : > /tmp/airspace-image-tags
  for img in "${IMAGES[@]}"; do
    local tag
    tag=$(docker image inspect -f '{{.Id}}' "$img:local" | cut -d: -f2 | cut -c1-12)
    docker tag "$img:local" "$img:$tag"
    if ! sudo k3s ctr -n k8s.io images ls -q "name==docker.io/library/$img:$tag" | grep -q .; then
      echo "importing $img:$tag"
      docker save "$img:$tag" | sudo k3s ctr -n k8s.io images import - >/dev/null
    fi
    echo "$img $tag" >> /tmp/airspace-image-tags
  done
}

# A git-ignored overlay that pins our images to the tags just built.
write_overlay() {
  mkdir -p infra/.deploy
  {
    echo "# Written by infra/k8s-apply.sh; not in git."
    echo "apiVersion: kustomize.config.k8s.io/v1beta1"
    echo "kind: Kustomization"
    echo "resources: [..]"
    echo "images:"
    while read -r img tag; do
      echo "  - name: $img"
      echo "    newTag: \"$tag\""
    done < /tmp/airspace-image-tags
  } > infra/.deploy/kustomization.yaml
}

# Local volumes need their directory. On the VM they exist since the cutover; on a fresh node
# they are created empty, owned by the user the pod runs as.
ensure_volumes() {
  sudo install -d -m 755 /srv/airspace
  for v in "${VOLUMES[@]}"; do
    read -r dir uid <<<"$v"
    sudo test -d "/srv/airspace/$dir" || sudo install -d -m 700 -o "$uid" -g "$uid" "/srv/airspace/$dir"
  done
}

main "$@"
