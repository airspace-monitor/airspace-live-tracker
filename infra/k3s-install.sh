#!/bin/bash
# One-time setup of k3s on the VM (docs/adr/0005-single-node-k3s.md). Safe to run again.
# Run on the VM as ubuntu: infra/k3s-install.sh
set -euo pipefail

K3S_VERSION=v1.36.6+k3s1
POD_CIDR=10.42.0.0/16
SERVICE_CIDR=10.43.0.0/16

# Oracle's Ubuntu image rejects everything not explicitly allowed in INPUT and FORWARD, which also
# drops traffic between pods. Allow the cluster's own ranges (never the internet) and persist it.
for cidr in "$POD_CIDR" "$SERVICE_CIDR"; do
  for chain in INPUT FORWARD; do
    sudo iptables -C "$chain" -s "$cidr" -j ACCEPT 2>/dev/null || sudo iptables -I "$chain" 1 -s "$cidr" -j ACCEPT
  done
  sudo iptables -C FORWARD -d "$cidr" -j ACCEPT 2>/dev/null || sudo iptables -I FORWARD 1 -d "$cidr" -j ACCEPT
done
if command -v netfilter-persistent >/dev/null; then sudo netfilter-persistent save >/dev/null; fi

# Traefik and ServiceLB are off: nothing is published to the internet. NodePorts listen on
# 127.0.0.1 only, and `tailscale serve` publishes them to the tailnet (infra/k3s-cutover.sh).
sudo install -d -m 755 /etc/rancher/k3s
sudo tee /etc/rancher/k3s/config.yaml >/dev/null <<EOF
write-kubeconfig-mode: "0600"
cluster-cidr: $POD_CIDR
service-cidr: $SERVICE_CIDR
disable:
  - traefik
  - servicelb
node-label:
  - airspace/role=server
kube-proxy-arg:
  - nodeport-addresses=127.0.0.0/8
secrets-encryption: true
EOF

if ! k3s --version 2>/dev/null | grep -q "${K3S_VERSION}"; then
  # The official installer verifies the binary's checksum; the version is pinned.
  curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION="$K3S_VERSION" sh -
fi
sudo k3s kubectl wait --for=condition=Ready node --all --timeout=5m

# kubectl for ubuntu (deploy.sh runs as ubuntu).
install -d -m 700 ~/.kube
sudo install -m 600 -o "$(id -u)" -g "$(id -g)" /etc/rancher/k3s/k3s.yaml ~/.kube/config

sudo install -d -m 755 /srv/airspace
kubectl get nodes -o wide
