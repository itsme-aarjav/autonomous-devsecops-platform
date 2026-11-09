# Live Evidence Screenshots Catalog

This directory contains 28 genuine, high-resolution visual proofs captured from the live AWS production environment (`boutique-dev-eks`, `us-east-2`, account `592668326948`) prior to the final cloud decommissioning.

Every image was captured personally between **01:21 AM and 04:11 AM IST on November 9, 2026** during live operational verification.

---

## Visual Proof Overview

| Category | Count | Files | Primary Systems Proven |
| :--- | :---: | :--- | :--- |
| **Storefront & End-to-End UI** | 1 | `01` | Live public e-commerce microservices application at `demo.aarjav.site` |
| **Argo CD GitOps Workloads** | 6 | `02`, `03`, `15`–`18` | Declarative GitOps, Ingress-to-Pod topology, StatefulSet, CronJob |
| **Grafana Live Observability** | 11 | `04`–`14` | Real-time cluster CPU/RAM, network packets, zero drops, storage IOPS, node health |
| **AWS Cloud Infrastructure** | 10 | `19`–`28` | VPC Resource Map, EKS Auto Mode cluster, ALBs, NAT GW, ECR, DynamoDB, SQS, S3, KMS |

---

## Screenshot Inventory & Verification Details

### 1. Storefront & End-to-End Application UI

#### `01-storefront-ui-demo.png`
- **Captured**: Nov 9, 2026 at 01:21:26 AM IST
- **URL**: `https://demo.aarjav.site`
- **What it proves**: Live, publicly reachable e-commerce microservices platform served via AWS ALB and Amazon Route 53. Displays the full boutique catalog with 8 luxury items (Vintage Typewriter, Terracotta Plant Pot, Artisan Leather Wallet, Mechanical Keyboard, etc.), live USD pricing, responsive CSS grid, shopping cart interface, and active session state.
- **Correlating Proof**: `proof/terminal-outputs/08-smoke-test-boutique.txt`

---

### 2. GitOps & Application Architecture (Argo CD)

#### `02-argocd-application-overview.png`
- **Captured**: Nov 9, 2026 at 01:55:19 AM IST
- **URL**: `https://argocd.demo.aarjav.site`
- **What it proves**: Argo CD Application tile for `boutique` showing `Healthy` and `Synced`. Linked directly to GitHub repository `itsme-aarjav/autonomous-devsecops-platform`, tracking target revision `HEAD` (commit `11283ea`), deploying into the `boutique` namespace.
- **Correlating Proof**: `proof/terminal-outputs/12-argocd-sync-verification.txt`

#### `03-argocd-network-topology.png`
- **Captured**: Nov 9, 2026 at 01:55:44 AM IST
- **What it proves**: Full Kubernetes network topology rendered by Argo CD: AWS Load Balancer Controller Ingress routing to the `boutique-frontend` Service, upstream Pod endpoints, and child replica sets.

#### `15-argocd-workloads-tree.png`
- **Captured**: Nov 9, 2026 at 02:05:46 AM IST
- **What it proves**: High-level workload hierarchy in Argo CD showing Deployments, ReplicaSets, and healthy Pod instances across microservices.

#### `16-argocd-auth-canary-gateway.png`
- **Captured**: Nov 9, 2026 at 02:05:55 AM IST
- **What it proves**: Declarative deployment of `boutique-auth`, `boutique-gateway`, and the `boutique-canary-trigger` ConfigMap managed by Argo CD.

#### `17-argocd-postgres-statefulset-pvc.png`
- **Captured**: Nov 9, 2026 at 02:06:00 AM IST
- **What it proves**: Database persistence tier: `boutique-postgres` StatefulSet, backing 20GB EBS PersistentVolumeClaim (`gp3`), dedicated Service, and configuration secrets.

#### `18-argocd-cronjob-monitoring-ingress.png`
- **Captured**: Nov 9, 2026 at 02:06:05 AM IST
- **What it proves**: Operational platform infrastructure: `boutique-backup-cronjob` (automated S3 backup), `PrometheusRule` alerting specifications, Ingress rules, and RBAC bindings.

---

### 3. Production Monitoring & Cluster Observability (Grafana)

#### `04-grafana-cluster-compute-resources.png`
- **Captured**: Nov 9, 2026 at 01:59:25 AM IST
- **URL**: `https://grafana.demo.aarjav.site`
- **What it proves**: Cluster-wide compute utilization: Cluster CPU Utilization at 2.74%, Cluster Memory Utilization at 20.5%, alongside requested CPU vs. hardware limits by namespace.

#### `05-grafana-cluster-memory-network.png`
- **Captured**: Nov 9, 2026 at 01:59:31 AM IST
- **What it proves**: Cluster-wide memory requests and total current network bandwidth allocation across system, monitoring, and application namespaces.

#### `06-grafana-cluster-container-bandwidth.png`
- **Captured**: Nov 9, 2026 at 01:59:38 AM IST
- **What it proves**: Granular container bandwidth received and transmitted per second, demonstrating low-latency pod communications.

#### `07-grafana-cluster-packet-metrics.png`
- **Captured**: Nov 9, 2026 at 01:59:42 AM IST
- **What it proves**: Network reliability: transmitted packet rates alongside **0 packet drops** across all Kubernetes worker nodes and namespaces.

#### `08-grafana-cluster-storage-iops.png`
- **Captured**: Nov 9, 2026 at 01:59:47 AM IST
- **What it proves**: Cluster storage performance: Storage IOPS and throughput across EBS gp3 volumes.

#### `09-grafana-boutique-pods-cpu-memory.png`
- **Captured**: Nov 9, 2026 at 02:00:36 AM IST
- **What it proves**: Pod-level resource metrics inside the `boutique` namespace: individual CPU and Memory utilization for frontend, auth, postgres, and aiops-assistant pods.

#### `10-grafana-boutique-pods-memory-network.png`
- **Captured**: Nov 9, 2026 at 02:00:49 AM IST
- **What it proves**: Pod memory quotas versus physical usage, showing healthy headroom and absence of memory pressure under standard traffic.

#### `11-grafana-boutique-pods-packet-health.png`
- **Captured**: Nov 9, 2026 at 02:01:32 AM IST
- **What it proves**: Pod-level packet transmission rates and confirmation of zero dropped network frames within the application namespace.

#### `12-grafana-boutique-pods-storage-io.png`
- **Captured**: Nov 9, 2026 at 02:01:44 AM IST
- **What it proves**: Postgres database pod disk I/O operations per second and read/write throughput metrics on EBS gp3.

#### `13-grafana-node-exporter-system-load.png`
- **Captured**: Nov 9, 2026 at 02:02:16 AM IST
- **What it proves**: Host-level metrics via Prometheus Node Exporter on EKS Bottlerocket worker node `ip-10-1-10-80.us-east-2.compute.internal`: CPU utilization 1.9%, 1-min load average 0.08, RAM utilization 14.6% (1.10 GiB of 7.55 GiB).

#### `14-grafana-node-exporter-network-disk.png`
- **Captured**: Nov 9, 2026 at 02:02:23 AM IST
- **What it proves**: Worker node hardware telemetry: network interface statistics across Elastic Network Interfaces (`eni-*`, `eth0`), disk throughput, and I/O latency.

---

### 4. Live AWS Cloud Management Console Proofs

#### `19-aws-vpc-resource-map.png`
- **Captured**: Nov 9, 2026 at 03:53:56 AM IST
- **AWS Console**: Amazon VPC > Your VPCs > `vpc-09b73c79412ad1f25 / boutique-dev-vpc`
- **What it proves**: VPC Resource Map in `us-east-2` showing 10.1.0.0/16 CIDR, 4 subnets (2 public, 2 private across AZs `us-east-2a` and `us-east-2b`), 3 route tables, Internet Gateway (`boutique-dev-vpc-igw`), NAT Gateway (`boutique-dev-vpc-nat-gw`), and S3 Gateway Endpoint (`boutique-dev-vpc-s3-gateway-endpoint`).
- **Correlating Proof**: `proof/terminal-outputs/01-terraform-persistent-state.txt`

#### `20-aws-eks-cluster-info.png`
- **Captured**: Nov 9, 2026 at 03:54:27 AM IST
- **AWS Console**: Amazon EKS > Clusters > `boutique-dev-eks`
- **What it proves**: Active EKS cluster ARN `arn:aws:eks:us-east-2:592668326948:cluster/boutique-dev-eks`, Kubernetes v1.36, EKS Auto Mode enabled, 26 Pods, 3 Nodes, 4 IAM access entries, 2 Pod Identities, and IAM role `boutique-dev-eks-cluster-role`.
- **Correlating Proof**: `proof/terminal-outputs/03-eks-cluster-status.txt`

#### `21-aws-eks-workloads-status.png`
- **Captured**: Nov 9, 2026 at 03:54:40 AM IST
- **AWS Console**: Amazon EKS > Clusters > `boutique-dev-eks` > Resources
- **What it proves**: EKS Workload status breakdown: 26 Pods (25 Running, 1 Succeeded), 14 Deployments (100% running), 4 StatefulSets (100% running), 1 DaemonSet, 51 ReplicaSets. Specifically displays `aiops-assistant-695f969694-8dqqm` and `alertmanager-kube-prometheus-stack-alertmanager-0` in Running state.
- **Correlating Proof**: `proof/terminal-outputs/04-k8s-pod-status.txt`

#### `22-aws-alb-load-balancers.png`
- **Captured**: Nov 9, 2026 at 04:06:22 AM IST
- **AWS Console**: Amazon EC2 > Load Balancers
- **What it proves**: 3 Active Application Load Balancers provisioned by AWS Load Balancer Controller in `vpc-09b73c79412ad1f25` across 2 AZs:
  1. `k8s-boutique-boutique-...` (Storefront ALB)
  2. `k8s-monitori-grafanai-...` (Grafana Observability ALB)
  3. `k8s-argocd-argocdin-...` (Argo CD GitOps ALB)
- **Correlating Proof**: `proof/terminal-outputs/07-alb-ingress-status.txt`

#### `23-aws-vpc-nat-gateway.png`
- **Captured**: Nov 9, 2026 at 04:06:51 AM IST
- **AWS Console**: Amazon VPC > NAT gateways > `nat-0f90877e6368c66d5 / boutique-dev-vpc-nat-gw`
- **What it proves**: Available public NAT Gateway associated with Elastic IP `3.12.199.177` in `subnet-06db1c0a8fbb3cdaf / boutique-dev-vpc-public-us-east-2a`, providing secure egress for private subnets.

#### `24-aws-ecr-repositories.png`
- **Captured**: Nov 9, 2026 at 04:07:10 AM IST
- **AWS Console**: Amazon ECR > Private repositories
- **What it proves**: 4 KMS-encrypted ECR repositories under account `592668326948`:
  1. `boutique-aiops-assistant`
  2. `boutique-auth`
  3. `boutique-frontend`
  4. `boutique-gateway`
- **Correlating Proof**: `proof/terminal-outputs/02-ecr-repositories.txt`

#### `25-aws-dynamodb-tables.png`
- **Captured**: Nov 9, 2026 at 04:07:29 AM IST
- **AWS Console**: Amazon DynamoDB > Tables
- **What it proves**: 3 Active on-demand DynamoDB tables storing the AIOps incident state machine:
  1. `boutique-aiops-episodes` (PK: `episode_id`)
  2. `boutique-aiops-rca-reports` (PK: `incident_id`)
  3. `boutique-aiops-remediations` (PK: `proposal_id`, 1 GSI)
- **Correlating Proof**: `proof/terminal-outputs/05-dynamodb-tables.txt`

#### `26-aws-sqs-fifo-queues.png`
- **Captured**: Nov 9, 2026 at 04:07:51 AM IST
- **AWS Console**: Amazon SQS > Queues
- **What it proves**: 2 SSE-KMS encrypted FIFO queues with dead-letter queue routing:
  1. `boutique-aiops-alert-queue.fifo`
  2. `boutique-aiops-alert-dlq.fifo`
- **Correlating Proof**: `proof/terminal-outputs/06-sqs-queues.txt`

#### `27-aws-s3-buckets-inventory.png`
- **Captured**: Nov 9, 2026 at 04:10:25 AM IST
- **AWS Console**: Amazon S3 > Buckets
- **What it proves**: Project S3 storage in `us-east-2`:
  - `boutique-aiops-backups-592668326948-us-east-2` (encrypted backups)
  - `boutique-aiops-node-diagnostics-us-east-2` (diagnostic runbooks)
  - `boutique-aiops-tfstate-us-east-2` (Terraform remote state)
  - (Also confirms clear separation from pre-existing `pokevault-*` buckets in `us-east-1`).
- **Correlating Proof**: `proof/terminal-outputs/01-terraform-persistent-state.txt`

#### `28-aws-kms-customer-managed-keys.png`
- **Captured**: Nov 9, 2026 at 04:10:55 AM IST
- **AWS Console**: AWS Key Management Service (KMS) > Customer managed keys
- **What it proves**: Active Customer Managed Key (CMK) `1e4e2ce3-e642-47a9-a20d-3a47b052918b` with alias `boutique-aiops-key` (Symmetric, SYMMETRIC_DEFAULT, Encrypt and decrypt), providing platform-wide envelope encryption for S3, SQS, ECR, and Secrets Manager.
- **Correlating Proof**: `proof/terminal-outputs/01-terraform-persistent-state.txt`
