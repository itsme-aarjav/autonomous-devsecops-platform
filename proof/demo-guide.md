# Historical Platform Verification Walkthrough

This guide documents the end-to-end verification walkthrough conducted when the platform was active on AWS.

---

## 1. Operational Status Notice

The cloud infrastructure has been decommissioned to maintain cost governance.

Live interactive testing via browser URLs is no longer active. Evaluators should review the visual screenshots in [`proof/`](README.md), terminal outputs in [`proof/terminal-outputs/`](terminal-outputs/README.md), and the GitHub pull requests and commit history.

---

## 2. Walkthrough Stages & Verified Evidence

During live verification on AWS EKS (`boutique-dev-eks`, `us-east-2`, account `592668326948`), the following capabilities were validated:

### Stage 1: Public HTTPS Storefront Verification
- **Test**: Sent HTTPS and plain HTTP requests to `demo.aarjav.site`.
- **Outcome**: Verified `HTTP/2 200 OK` with AWS Certificate Manager TLS termination and automatic `301 Moved Permanently` redirect on plain HTTP.
- **Evidence**: [Storefront Screenshot](architecture/01-storefront-ui-demo.png) &bull; [Storefront API Log](terminal-outputs/05-storefront-api.txt).

### Stage 2: E-Commerce Catalog & Transactional PostgreSQL
- **Test**: Queried `GET /api/products` and placed authenticated test orders with the pre-seeded demo user.
- **Outcome**: Retrieved all 8 seeded luxury boutique products (Silk Evening Gown, Cashmere Blend Overcoat, Italian Leather Handbag, Stiletto Designer Heels, Diamond Solitaire Necklace, Classic Tailored Wool Blazer, Signature Leather Wallet, Akoya Pearl Drop Earrings). Verified atomic inventory deduction using `SELECT ... FOR UPDATE` in PostgreSQL 15.
- **Evidence**: [Storefront API Log](terminal-outputs/05-storefront-api.txt).

### Stage 3: Observability & Telemetry Dashboards
- **Test**: Inspected real-time metrics in Grafana (`grafana.demo.aarjav.site`) and Prometheus.
- **Outcome**: Verified live CPU utilization (2.74%), memory utilization (20.5%), storage IOPS, and zero packet drops across all Kubernetes worker nodes.
- **Evidence**: [Grafana Metrics Screenshot](monitoring/04-grafana-cluster-compute-resources.png) &bull; [Observability Baseline Log](terminal-outputs/06-observability-baseline.txt).

### Stage 4: GitOps Application Synchronization
- **Test**: Inspected Argo CD (`argocd.demo.aarjav.site`) for Git-to-cluster synchronization.
- **Outcome**: Confirmed `boutique` application state as `Healthy` and `Synced`, matching Git commit `11283ea` on `main`. Verified Argo Rollouts canary topology.
- **Evidence**: [Argo CD Overview Screenshot](ci-cd/02-argocd-application-overview.png) &bull; [Argo CD Topology Screenshot](ci-cd/03-argocd-network-topology.png).

### Stage 5: AIOps Incident Detection & GitOps Self-Healing
- **Test**: Injected canary memory stress, triggering a Pod OOMKilled alert.
- **Outcome**: Prometheus detected the failure; Alertmanager routed the incident via SQS FIFO; the LangGraph assistant analyzed telemetry using Amazon Bedrock Nova Lite; an operator reviewed the proposal in CloudShell CLI and approved it with HMAC token; a reviewed Pull Request was opened, merged, and reconciled by Argo CD.
- **Evidence**: [AIOps Terminal Logs](terminal-outputs/README.md) (Logs 08–34).

### Stage 6: Database Disaster Recovery Verification
- **Test**: Tested automated point-in-time database restoration in an isolated test environment.
- **Outcome**: Verified that KMS-encrypted PostgreSQL S3 SQL dumps (`auth_db_backup_20261108_203012Z.sql.gz`) can be fully restored in an ephemeral pod, validating schema and all 8 products without touching live production.
- **Evidence**: [Isolated Restore Log](terminal-outputs/35-isolated-backup-restore-verification.txt).

### Stage 7: Cost Elimination & Cloud Decommissioning
- **Test**: Decommissioned all active AWS infrastructure.
- **Outcome**: Destroyed EKS cluster, worker nodes, ALBs, NAT Gateway, ECR repos, and DynamoDB tables. Reduced recurring AWS spend to an estimated residual < $0.01/month.
- **Evidence**: [Cloud Teardown Log](terminal-outputs/36-aws-teardown-and-cost-elimination.txt).
