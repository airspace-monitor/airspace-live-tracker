#!/bin/bash
# Deploys main to k3s on the VM (docs/01-architecture.md#deployment, docs/adr/0005-single-node-k3s.md):
# pull the code, then infra/k8s-apply.sh builds and imports the images, runs migrations before the
# new code starts, applies the manifests and waits for the rollout.
# Run by hand or by deploy.yml over Tailscale. Safe to run again: each step is idempotent.
set -euo pipefail

# Everything is inside main(), so bash has read the whole script before `git merge` can change it.
main() {
  cd "$(dirname "$0")/.."
  command -v k3s >/dev/null || { echo "k3s is not installed: run infra/k3s-install.sh, then infra/k3s-cutover.sh" >&2; exit 1; }

  exec 9>/tmp/airspace-deploy.lock
  flock -n 9 || { echo "another deploy is running" >&2; exit 1; }

  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "local changes in $(pwd); commit them through a PR or discard them first:" >&2
    git status --short --untracked-files=no >&2
    exit 1
  fi
  git fetch --quiet origin main
  git checkout --quiet main
  git merge --quiet --ff-only origin/main
  echo "deploying $(git log --oneline -1)"

  # A new process, so the k8s-apply.sh just merged is the one that runs.
  bash infra/k8s-apply.sh infra/.env
  docker image prune -f >/dev/null
}

main "$@"
exit
