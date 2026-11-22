# ADR-0005 · Run the server stack on single-node k3s

**Status:** accepted · 2026-11-22 · supersedes the "docker compose" part of [ADR-0004](0004-hosting-oracle-free-tier.md) (hosting stays on the Oracle VM)

## Context
- The course feedback (2026-11) said a single Docker Compose setup does not show the cloud aspects of the system, and that the architecture shows no principles of scalability. The course grades the deployment strategy (autoscaling, region, sustainability) and asks for automatic redeployment under a simulated carbon signal while keeping SLOs.
- Oracle cut the Always Free Ampere A1 allowance to 1,500 OCPU-hours and 9,000 GB-hours a month, which is 2 OCPU and 12 GB in total ([Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm), checked 2026-11-22). Our VM already uses all of it, and its 200 GB boot volume uses the whole 200 GB block-storage allowance. A second free node in our tenancy is not possible, and nothing may be billed.
- The collector must stay on the Raspberry Pi at home, because OpenSky blocks data-centre IPs ([ADR-0001](0001-home-collectors-push-to-cloud.md)).

## Decision
Run every server service as Kubernetes workloads on **k3s**, with the existing Oracle VM as the only node.

- **One node, many pods.** Each Compose service becomes its own workload with CPU and memory requests and limits, readiness and liveness probes, and an update strategy: Deployments for the stateless services, a StatefulSet for the database.
- **Autoscaling where it is safe.** public-api is stateless and gets a HorizontalPodAutoscaler (1–3 replicas on CPU). ingest-api, stream-worker, the Dagster daemon and Grafana stay at one replica on purpose: the stream-worker and the Dagster daemon must be single consumers, and Grafana keeps SQLite state on a volume.
- **State stays on the VM's disk.** Postgres, Dagster storage and Grafana data are local PersistentVolumes in `/srv/airspace/` on the node labelled `airspace/role=server`. The cutover moves the existing Docker volumes there without copying the data.
- **Nothing new is exposed.** Services that people reach are NodePorts bound to `127.0.0.1` only (`nodeport-addresses`), and `tailscale serve` keeps publishing the same tailnet ports as before (8000, 8001, 3000, 3001). The Pi's `INGEST_URL` does not change.
- **No registry yet.** `infra/deploy.sh` builds our images with Docker on the VM, tags them by image ID, imports them into k3s's containerd and applies the Kustomize manifests in `infra/`. Third-party images are pulled by tag as before.
- **Secrets stay out of git.** `deploy.sh` turns `infra/.env` into the `airspace-env` Secret on each deploy.
- **Compose stays for local development and CI** (`infra/test-db.sh`). The Kubernetes manifests are the production definition. Both are kept in step in the same PR.
- **The Pi is an edge node in the architecture, not a cluster member (yet).** It keeps running the collector in Docker. Joining it as a k3s agent is a later, optional step: only the collector would run there, as a DaemonSet that keeps running while the Pi is cut off from the control plane, because every other service needs low-latency access to the database on the VM.

## Consequences
- The system is described and operated as Kubernetes workloads: probes restart unhealthy pods, rolling updates replace the stateless services without downtime, and public-api scales out under load. The carbon-aware behaviour (planned, [10](../10-roadmap.md)) acts on these workloads: it scales or reconfigures Deployments and delays Dagster jobs, instead of moving work between nodes.
- **No failover.** One node is still one machine; if the VM goes down, everything on it goes down. Collection is not affected: the Pi spools and uploads later ([04](../04-pipelines.md#catch-up-after-an-outage-or-the-m0-backlog)).
- **Scale-out path.** More capacity means joining agent nodes (`k3s agent` with the server's token, over Tailscale). The stateless services spread without changes; the database is the only workload pinned to a node, and would move to a replica or a managed service at larger scale.
- k3s adds about 0.6 GB of RAM on the VM. The stack used about 2.4 GB on 2026-11-22, so the 12 GB node has room.
- Two definitions of the stack exist (Compose for dev and CI, Kustomize for production). CI validates the manifests with kubeconform so they cannot silently break.
- Alternatives considered:
  - **Docker Compose (status quo):** simplest, but rejected by the course feedback and offers no scaling or self-healing model.
  - **OKE (Oracle's managed Kubernetes), Basic cluster:** the control plane is free, but worker nodes must fit in the same 2 OCPU, Basic clusters cannot add the Pi or nodes from other providers, and moving to OKE means rebuilding the VM and restoring the database.
  - **k3s with a second cloud node:** the honest multi-node setup, but a second Oracle node is no longer free in our tenancy, and the other providers' free tiers are credits that expire or VMs too small (1 GB).
  - **k3s with the Pi as a second node now:** a real edge node, but only the collector can run there, so it adds risk to the one component that must not break, for little gain. Kept as a later step.
  - **Local minikube or kind only:** shows Kubernetes but not on the cloud server, and the running system would still be Compose.
