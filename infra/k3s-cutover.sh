#!/bin/bash
# One-time move of the running stack from Docker Compose to k3s (docs/adr/0005-single-node-k3s.md).
# Run on the VM as ubuntu after infra/k3s-install.sh: infra/k3s-cutover.sh
#
# The collector keeps spooling on the Pi while ingest-api is down and uploads the backlog afterwards,
# so no positions are lost. Rollback: infra/k3s-cutover.sh --rollback (moves the data back, starts
# Compose and points `tailscale serve` at it again).
set -euo pipefail
cd "$(dirname "$0")"

VOLUMES=(db-data dagster-storage grafana-data)
# tailnet port -> Compose host port / k3s NodePort (127.0.0.1 only)
PORTS=("8000 8000 30800" "8001 8001 30801" "3000 3000 30300" "3001 3001 30301")

serve() {  # serve <column: 2 = compose, 3 = k3s>
  for p in "${PORTS[@]}"; do
    read -r public compose k3s <<<"$p"
    local target=$compose; [ "$1" = 3 ] && target=$k3s
    sudo tailscale serve --bg --tcp "$public" "tcp://localhost:$target" >/dev/null
  done
  tailscale serve status
}

if [ "${1:-}" = "--rollback" ]; then
  kubectl delete -k ../.deploy --ignore-not-found --wait=true || true
  for v in "${VOLUMES[@]}"; do
    src=/srv/airspace/$v dst=/var/lib/docker/volumes/airspace_$v/_data
    if sudo test -d "$src"; then sudo rmdir "$dst" 2>/dev/null || true; sudo mv "$src" "$dst"; fi
  done
  docker compose up -d --wait
  serve 2
  exit
fi

command -v k3s >/dev/null || { echo "run infra/k3s-install.sh first" >&2; exit 1; }

# 1. Stop Compose. Volumes are kept (no -v).
docker compose --profile tools stop
docker compose down --remove-orphans

# 2. Move each volume's data into /srv/airspace. Same filesystem, so mv is instant and keeps
#    ownership (postgres 1000, dagster 10002, grafana 472).
for v in "${VOLUMES[@]}"; do
  src=/var/lib/docker/volumes/airspace_$v/_data dst=/srv/airspace/$v
  if sudo test -d "$dst"; then
    echo "$dst already exists, leaving it"
  else
    sudo mv "$src" "$dst"
    sudo install -d "$src"  # Docker expects the volume directory to exist
  fi
  sudo stat -c '%n %U:%G' "$dst"
done

# 3. Deploy to k3s (builds, imports, migrates, applies, waits).
./deploy.sh

# 4. Point the tailnet ports at the NodePorts. The Pi's INGEST_URL stays the same.
serve 3
