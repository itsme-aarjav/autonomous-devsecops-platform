# Master Evidence Screenshots Index

This directory serves as the centralized visual evidence index for the **Autonomous DevSecOps & Cloud Operations Platform**.

All **28 genuine, high-resolution screenshots** captured during live cloud operation on Amazon EKS (`boutique-dev-eks`, `us-east-2`, account `592668326948`) on November 9, 2026, prior to cloud decommissioning, are organized into their respective dedicated proof categories across the repository.

---

## 1. Categorized Visual Evidence Summary

| Proof Category | Count | Directory | Primary Capabilities Demonstrated |
| :--- | :---: | :--- | :--- |
| **A. CI/CD & GitOps** | 7 | [`proof/ci-cd/`](../ci-cd/) | Argo CD application state, Ingress-to-Pod network topologies, microservice trees, StatefulSet, CronJob, and AWS ECR KMS repositories. |
| **B. Observability & SRE** | 11 | [`proof/monitoring/`](../monitoring/) | Grafana cluster compute, memory/network quotas, container packet rates, zero packet drops, storage IOPS, pod quotas, and Node Exporter host telemetry. |
| **C. Kubernetes Health** | 2 | [`proof/kubernetes/`](../kubernetes/) | AWS EKS Auto Mode cluster configuration, Kubernetes v1.36 runtime, node status, and 26 healthy workload pods. |
| **D. Cloud Architecture** | 6 | [`proof/architecture/`](../architecture/) | Live boutique storefront UI (`demo.aarjav.site`), AWS VPC 4-subnet resource map, 3 active ALBs, NAT Gateway, DynamoDB tables, and SQS FIFO queues. |
| **E. Backup & Storage** | 1 | [`proof/backup-recovery/`](../backup-recovery/) | Project Amazon S3 bucket inventory (encrypted backup, diagnostics, tfstate storage). *(See terminal log 35 for SQL restore evidence).* |
| **F. Security & KMS** | 1 | [`proof/security/`](../security/) | AWS KMS Customer Managed Key (CMK `1e4e2ce3-...`, alias `boutique-aiops-key`) providing platform-wide envelope encryption. |
| **Total Visual Proofs** | **28** | | **All 28 screenshots accounted for across dedicated proof directories.** |

---

## 2. Complete Screenshot Inventory & Verified Links

### A. CI/CD & GitOps (`proof/ci-cd/`)

| File & Valid Link | Capture Timestamp | Operational Evidence Demonstrated | Correlating Terminal Log |
| :--- | :---: | :--- | :--- |
| [`02-argocd-application-overview.png`](../ci-cd/02-argocd-application-overview.png) | 01:55:19 AM IST | Argo CD `boutique` tile: `Healthy` and `Synced`, tracking `main` at commit `11283ea`. | [`04-argo-image-parity.txt`](../terminal-outputs/04-argo-image-parity.txt) |
| [`03-argocd-network-topology.png`](../ci-cd/03-argocd-network-topology.png) | 01:55:44 AM IST | Visual network topology: AWS Load Balancer Controller Ingress → `boutique-frontend` Service → Pod endpoints. | [`03-kubernetes-workloads.txt`](../terminal-outputs/03-kubernetes-workloads.txt) |
| [`15-argocd-workloads-tree.png`](../ci-cd/15-argocd-workloads-tree.png) | 02:05:46 AM IST | Workload hierarchy of Deployments, ReplicaSets, and healthy Pod instances in Argo CD. | [`03-kubernetes-workloads.txt`](../terminal-outputs/03-kubernetes-workloads.txt) |
| [`16-argocd-auth-canary-gateway.png`](../ci-cd/16-argocd-auth-canary-gateway.png) | 02:05:55 AM IST | Workload tree for `boutique-auth`, `boutique-gateway`, and the `boutique-canary-trigger` ConfigMap. | [`03-kubernetes-workloads.txt`](../terminal-outputs/03-kubernetes-workloads.txt) |
| [`17-argocd-postgres-statefulset-pvc.png`](../ci-cd/17-argocd-postgres-statefulset-pvc.png) | 02:06:00 AM IST | Database persistence tier: `boutique-postgres` StatefulSet, 20GB EBS PVC (`gp3`), Service, and secrets. | [`03-kubernetes-workloads.txt`](../terminal-outputs/03-kubernetes-workloads.txt) |
| [`18-argocd-cronjob-monitoring-ingress.png`](../ci-cd/18-argocd-cronjob-monitoring-ingress.png) | 02:06:05 AM IST | Operational infrastructure: `boutique-backup-cronjob`, `PrometheusRule` alerting specifications, Ingress, and RBAC. | [`03-kubernetes-workloads.txt`](../terminal-outputs/03-kubernetes-workloads.txt) |
| [`24-aws-ecr-repositories.png`](../ci-cd/24-aws-ecr-repositories.png) | 04:07:10 AM IST | AWS ECR Console: 4 KMS-encrypted private repositories (`boutique-aiops-assistant`, `boutique-auth`, `boutique-frontend`, `boutique-gateway`). | [`04-argo-image-parity.txt`](../terminal-outputs/04-argo-image-parity.txt) |

---

### B. Observability & SRE (`proof/monitoring/`)

| File & Valid Link | Capture Timestamp | Operational Evidence Demonstrated | Correlating Terminal Log |
| :--- | :---: | :--- | :--- |
| [`04-grafana-cluster-compute-resources.png`](../monitoring/04-grafana-cluster-compute-resources.png) | 01:59:25 AM IST | Cluster compute utilization: CPU Utilization at 2.74%, Memory Utilization at 20.5%, requested vs limits by namespace. | [`06-observability-baseline.txt`](../terminal-outputs/06-observability-baseline.txt) |
| [`05-grafana-cluster-memory-network.png`](../monitoring/05-grafana-cluster-memory-network.png) | 01:59:31 AM IST | Cluster memory requests and current network bandwidth distribution across namespaces. | [`06-observability-baseline.txt`](../terminal-outputs/06-observability-baseline.txt) |
| [`06-grafana-cluster-container-bandwidth.png`](../monitoring/06-grafana-cluster-container-bandwidth.png) | 01:59:38 AM IST | Granular container bandwidth received and transmitted per second across pods. | [`06-observability-baseline.txt`](../terminal-outputs/06-observability-baseline.txt) |
| [`07-grafana-cluster-packet-metrics.png`](../monitoring/07-grafana-cluster-packet-metrics.png) | 01:59:42 AM IST | Network reliability: transmitted packet rates alongside **0 packet drops** across all worker nodes. | [`06-observability-baseline.txt`](../terminal-outputs/06-observability-baseline.txt) |
| [`08-grafana-cluster-storage-iops.png`](../monitoring/08-grafana-cluster-storage-iops.png) | 01:59:47 AM IST | Cluster storage performance: Storage IOPS and read/write throughput across EBS `gp3` volumes. | [`06-observability-baseline.txt`](../terminal-outputs/06-observability-baseline.txt) |
| [`09-grafana-boutique-pods-cpu-memory.png`](../monitoring/09-grafana-boutique-pods-cpu-memory.png) | 02:00:36 AM IST | Pod-level metrics in `boutique` namespace: CPU and Memory utilization for frontend, auth, postgres, and aiops pods. | [`06-observability-baseline.txt`](../terminal-outputs/06-observability-baseline.txt) |
| [`10-grafana-boutique-pods-memory-network.png`](../monitoring/10-grafana-boutique-pods-memory-network.png) | 02:00:49 AM IST | Pod memory quotas vs physical usage, showing healthy headroom and absence of memory pressure. | [`06-observability-baseline.txt`](../terminal-outputs/06-observability-baseline.txt) |
| [`11-grafana-boutique-pods-packet-health.png`](../monitoring/11-grafana-boutique-pods-packet-health.png) | 02:01:32 AM IST | Pod-level packet transmission rates and confirmation of zero dropped network frames in application namespace. | [`06-observability-baseline.txt`](../terminal-outputs/06-observability-baseline.txt) |
| [`12-grafana-boutique-pods-storage-io.png`](../monitoring/12-grafana-boutique-pods-storage-io.png) | 02:01:44 AM IST | Postgres database pod disk I/O operations per second and read/write throughput on EBS `gp3`. | [`06-observability-baseline.txt`](../terminal-outputs/06-observability-baseline.txt) |
| [`13-grafana-node-exporter-system-load.png`](../monitoring/13-grafana-node-exporter-system-load.png) | 02:02:16 AM IST | Worker node `ip-10-1-10-80`: CPU 1.9%, 1-min load 0.08, RAM utilization 14.6% (1.10 GiB of 7.55 GiB). | [`06-observability-baseline.txt`](../terminal-outputs/06-observability-baseline.txt) |
| [`14-grafana-node-exporter-network-disk.png`](../monitoring/14-grafana-node-exporter-network-disk.png) | 02:02:23 AM IST | Node hardware telemetry: Elastic Network Interfaces (`eni-*`, `eth0`), disk throughput, and I/O latency. | [`06-observability-baseline.txt`](../terminal-outputs/06-observability-baseline.txt) |

---

### C. Kubernetes Cluster Health (`proof/kubernetes/`)

| File & Valid Link | Capture Timestamp | Operational Evidence Demonstrated | Correlating Terminal Log |
| :--- | :---: | :--- | :--- |
| [`20-aws-eks-cluster-info.png`](../kubernetes/20-aws-eks-cluster-info.png) | 03:54:27 AM IST | AWS EKS Console: `boutique-dev-eks` in `us-east-2`, Active, k8s v1.36, 26 Pods, 3 Nodes, Auto Mode enabled. | [`02-aws-eks-baseline.txt`](../terminal-outputs/02-aws-eks-baseline.txt) |
| [`21-aws-eks-workloads-status.png`](../kubernetes/21-aws-eks-workloads-status.png) | 03:54:40 AM IST | EKS Workloads Status: 26 Pods (25 Running, 1 Succeeded), 14 Deployments, showing `aiops-assistant` running. | [`03-kubernetes-workloads.txt`](../terminal-outputs/03-kubernetes-workloads.txt) |

---

### D. Platform & Cloud Architecture (`proof/architecture/`)

| File & Valid Link | Capture Timestamp | Operational Evidence Demonstrated | Correlating Terminal Log |
| :--- | :---: | :--- | :--- |
| [`01-storefront-ui-demo.png`](../architecture/01-storefront-ui-demo.png) | 01:21:26 AM IST | Live boutique storefront at `https://demo.aarjav.site` showing 8 seeded luxury products (Silk Evening Gown, Cashmere Blend Overcoat, Italian Leather Handbag, Stiletto Designer Heels, Diamond Solitaire Necklace, Classic Tailored Wool Blazer, Signature Leather Wallet, Akoya Pearl Drop Earrings) with live USD pricing, cart UI, and active session. | [`05-storefront-api.txt`](../terminal-outputs/05-storefront-api.txt) |
| [`19-aws-vpc-resource-map.png`](../architecture/19-aws-vpc-resource-map.png) | 03:53:56 AM IST | AWS VPC Console: `boutique-dev-vpc` (10.1.0.0/16) resource map: subnets across 2 AZs, route tables, IGW, NAT Gateway, S3 Gateway Endpoint. | [`01-github-ci-baseline.txt`](../terminal-outputs/01-github-ci-baseline.txt) |
| [`22-aws-alb-load-balancers.png`](../architecture/22-aws-alb-load-balancers.png) | 04:06:22 AM IST | AWS EC2 Console: 3 Active ALBs in `vpc-09b73c79412ad1f25` for Storefront, Grafana, and Argo CD. | [`03-kubernetes-workloads.txt`](../terminal-outputs/03-kubernetes-workloads.txt) |
| [`23-aws-vpc-nat-gateway.png`](../architecture/23-aws-vpc-nat-gateway.png) | 04:06:51 AM IST | AWS VPC Console: `boutique-dev-vpc-nat-gw` (EIP `3.12.199.177`) in public subnet `subnet-06db1c0a8fbb3cdaf`. | [`01-github-ci-baseline.txt`](../terminal-outputs/01-github-ci-baseline.txt) |
| [`25-aws-dynamodb-tables.png`](../architecture/25-aws-dynamodb-tables.png) | 04:07:29 AM IST | AWS DynamoDB Console: 3 Active on-demand tables (`boutique-aiops-episodes`, `boutique-aiops-rca-reports`, `boutique-aiops-remediations`). | [`14-aiops-dynamodb-proposal.txt`](../terminal-outputs/14-aiops-dynamodb-proposal.txt) |
| [`26-aws-sqs-fifo-queues.png`](../architecture/26-aws-sqs-fifo-queues.png) | 04:07:51 AM IST | AWS SQS Console: 2 SSE-KMS encrypted FIFO queues (`boutique-aiops-alert-queue.fifo`, `boutique-aiops-alert-dlq.fifo`). | [`13-aiops-processing.txt`](../terminal-outputs/13-aiops-processing.txt) |

---

### E. Backup & Storage Resources (`proof/backup-recovery/`)

| File & Valid Link | Capture Timestamp | Operational Evidence Demonstrated | Correlating Terminal Log |
| :--- | :---: | :--- | :--- |
| [`27-aws-s3-buckets-inventory.png`](../backup-recovery/27-aws-s3-buckets-inventory.png) | 04:10:25 AM IST | AWS S3 Console: Project storage buckets in `us-east-2` (`boutique-aiops-backups-592668326948-us-east-2`, `boutique-aiops-node-diagnostics-us-east-2`, `boutique-aiops-tfstate-us-east-2`). *(Note: This bucket inventory proves storage resource existence; actual end-to-end database SQL restore verification is proven in terminal log 35).* | [`35-isolated-backup-restore-verification.txt`](../terminal-outputs/35-isolated-backup-restore-verification.txt) |

---

### F. Security & Cryptographic Keys (`proof/security/`)

| File & Valid Link | Capture Timestamp | Operational Evidence Demonstrated | Correlating Terminal Log |
| :--- | :---: | :--- | :--- |
| [`28-aws-kms-customer-managed-keys.png`](../security/28-aws-kms-customer-managed-keys.png) | 04:10:55 AM IST | AWS KMS Console: Customer Managed Key `1e4e2ce3-e642-47a9-a20d-3a47b052918b` (alias `boutique-aiops-key`), Enabled, Symmetric, providing envelope encryption for S3, SQS, ECR, and Secrets Manager. | [`01-github-ci-baseline.txt`](../terminal-outputs/01-github-ci-baseline.txt) |

---

> [!NOTE]
> **FinOps & Cost Proofs Directory (`proof/cost/`)**:
> Per project guidelines, `proof/cost/` holds the detailed FinOps economic model and cost governance documentation ([`proof/cost/finops-cost-model.md`](../cost/finops-cost-model.md)) and teardown cost verification ([`proof/terminal-outputs/36-aws-teardown-and-cost-elimination.txt`](../terminal-outputs/36-aws-teardown-and-cost-elimination.txt)). No unrelated screenshots have been placed in `proof/cost/`.
