# Autonomous DevSecOps & Cloud Operations Platform — Evaluator Evidence Package

> **Cloud Verification Evidence**: Historically deployed and verified on live AWS infrastructure (`boutique-dev-eks`, `us-east-2`, account `592668326948`).
> **Public HTTPS Endpoints Tested**: `https://demo.aarjav.site` | `https://argocd.demo.aarjav.site` | `https://grafana.demo.aarjav.site`
> **Current Cloud Status**: Complete live operational verification executed. Infrastructure intentionally decommissioned to eliminate recurring AWS costs (estimated project-only residual cost < $0.01/mo, pending AWS billing confirmation, excluding pre-existing account resources). All 28 visual proofs and 38 terminal execution logs are permanently cataloged below.

---

## 1. Executive Summary & Capabilities Demonstrated

This repository and evaluation package represent a complete, end-to-end implementation of modern cloud engineering, DevSecOps, and platform operations. Built to demonstrate production-grade cloud engineering practices, the platform addresses real-world challenges in cloud infrastructure provisioning, CI/CD pipeline scalability, container security, and autonomous operations.

```
                               ┌───────────────────────────────────────────┐
                               │    Public HTTPS: https://demo.aarjav.site │
                               └─────────────────────┬─────────────────────┘
                                                     │
                       ┌─────────────────────────────▼─────────────────────────────┐
                       │    AWS Application Load Balancer (EKS Auto Mode Ingress)   │
                       └─────────────────────────────┬─────────────────────────────┘
                                                     │
        ┌────────────────────────────────────────────┴────────────────────────────────────────────┐
        │                                                                                         │
 ┌──────▼──────────────────┐                                                       ┌──────────────▼────────────┐
 │   Boutique Frontend     │                                                       │     API Gateway / Auth    │
 │  (React / Non-Root UID) │                                                       │   (TypeScript / PG 15.19) │
 └─────────────────────────┘                                                       └──────────────┬────────────┘
                                                                                                  │
                                             ┌────────────────────────────────────────────────────┴────────────┐
                                             │                                                                 │
                              ┌──────────────▼──────────────┐                                   ┌──────────────▼──────────────┐
                              │     Prometheus Operator     │                                   │   PostgreSQL 15.19 Database │
                              │   (kube-prometheus-stack)   │                                   │   (20Gi KMS-Encrypted EBS)  │
                              └──────────────┬──────────────┘                                   └─────────────────────────────┘
                                             │ Alert Webhook
                              ┌──────────────▼──────────────┐
                              │    Amazon SQS FIFO Queue    │
                              │ (Deduplication + Encryption)│
                              └──────────────┬──────────────┘
                                             │ Async Consume
                              ┌──────────────▼──────────────┐
                              │       AIOps Assistant       │◄─────────────┐ Diagnostic Queries
                              │  (FastAPI / Python 3.11)    │              │ (K8s API + Prometheus)
                              └──────────────┬──────────────┘──────────────┘
                                             │
                                             ├─────────────────────────────┐
                                             ▼                             ▼
                              ┌─────────────────────────────┐┌───────────────────────────┐
                              │   Amazon Bedrock Converse   ││   Amazon DynamoDB Stores  │
                              │  (Amazon Nova Lite v1:0)    ││   (Episodes & RCA Reports)│
                              └─────────────────────────────┘└───────────────────────────┘
```

---

## 2. Platform Highlights

| Domain | Implementation & Technology | Evidence Reference |
| :--- | :--- | :--- |
| **E-Commerce Application** | Relational products catalog (8 seeded luxury items), atomic inventory locking (`SELECT FOR UPDATE`), demo checkout, order history | [`proof/architecture/01-storefront-ui-demo.png`](architecture/01-storefront-ui-demo.png) |
| **Cloud Infrastructure** | 3-Layer Terraform (Persistent, Dev, Add-ons), AWS VPC (4 subnets across 2 AZs), EKS Auto Mode, Bottlerocket OS | [`proof/architecture/19-aws-vpc-resource-map.png`](architecture/19-aws-vpc-resource-map.png), [`proof/kubernetes/20-aws-eks-cluster-info.png`](kubernetes/20-aws-eks-cluster-info.png) |
| **Public HTTPS Access** | AWS ACM TLS (RSA 2048), Route 53 Alias, EKS Auto Mode ALB, 100% healthy target groups | [`proof/architecture/22-aws-alb-load-balancers.png`](architecture/22-aws-alb-load-balancers.png) |
| **GitOps Continuous Delivery**| Argo CD 10.11.6 & Argo Rollouts 2.43.9 for canary progressive delivery (50% &rarr; 100%) and automated rollback | [`proof/ci-cd/02-argocd-application-overview.png`](ci-cd/02-argocd-application-overview.png), [`proof/ci-cd/03-argocd-network-topology.png`](ci-cd/03-argocd-network-topology.png) |
| **CI/CD & OIDC Security** | GitHub Actions decoupled pipelines, GitHub OIDC (zero static AWS keys), 10/10 green checks | [`proof/terminal-outputs/01-github-ci-baseline.txt`](terminal-outputs/01-github-ci-baseline.txt) |
| **Observability & SRE** | Prometheus Operator, Grafana (11 dashboard views), Node Exporter, kube-state-metrics, custom ServiceMonitors | [`proof/monitoring/04-grafana-cluster-compute-resources.png`](monitoring/04-grafana-cluster-compute-resources.png) |
| **Autonomous AIOps Engine**| Prometheus &rarr; Alertmanager &rarr; SQS FIFO &rarr; Bedrock Nova Lite &rarr; DynamoDB RCA &rarr; Operator CLI PR | [`proof/terminal-outputs/13-aiops-processing.txt`](terminal-outputs/13-aiops-processing.txt), [`proof/terminal-outputs/30-aiops-human-approval-pr.txt`](terminal-outputs/30-aiops-human-approval-pr.txt) |
| **Disaster Recovery** | Verified restoration of KMS-encrypted S3 PostgreSQL SQL dump (`auth_db_backup_20261108_203012Z.sql.gz`) in isolated ephemeral pod, plus EBS snapshot recovery (`snap-05a3b0ffe3463e280`) | [`proof/terminal-outputs/35-isolated-backup-restore-verification.txt`](terminal-outputs/35-isolated-backup-restore-verification.txt), [`proof/backup-recovery/restore-verification.md`](backup-recovery/restore-verification.md) |
| **DevSecOps & Hardening** | Restricted Pod Security Standards, non-root UID 10001, Trivy scanning, AWS KMS CMKs | [`proof/security/28-aws-kms-customer-managed-keys.png`](security/28-aws-kms-customer-managed-keys.png) |
| **FinOps Cost Governance**| Safe infrastructure decommissioning reducing recurring cloud spend from ~$341/mo to estimated residual < $0.01/mo | [`proof/terminal-outputs/36-aws-teardown-and-cost-elimination.txt`](terminal-outputs/36-aws-teardown-and-cost-elimination.txt) |

---

## 3. Evaluation & Verification Index

Every operational capability is verified with genuine, high-resolution visual evidence and terminal logs:

- **Evidence Catalogs**:
  - [`proof/screenshots/README.md`](screenshots/README.md): Master index of all 28 screenshots categorized across `ci-cd/`, `monitoring/`, `kubernetes/`, `architecture/`, `backup-recovery/`, and `security/`.
  - [`proof/terminal-outputs/README.md`](terminal-outputs/README.md): Master transcript index of all 36 numbered proof stages (across 38 `.txt` logs) detailing the 16-step incident and recovery lifecycle.
- **Deep-Dive Engineering Documentation**:
  - [`proof/ci-cd/ci-cd-architecture.md`](ci-cd/ci-cd-architecture.md): Decoupled pipeline design, OIDC integration, and GitOps parity.
  - [`proof/monitoring/observability-stack.md`](monitoring/observability-stack.md): ServiceMonitors, Prometheus rules, and Alertmanager routing topology.
  - [`proof/kubernetes/cluster-inventory.md`](kubernetes/cluster-inventory.md): Live node list, 26 pods across 4 namespaces, Ingress, and PV/PVC status.
  - [`proof/architecture/system-architecture.md`](architecture/system-architecture.md): Complete cloud and network topology.
  - [`proof/architecture/aiops-pipeline.md`](architecture/aiops-pipeline.md): Event-driven AIOps sequence diagram, deduplication, and LLM reasoning flow.
  - [`proof/backup-recovery/restore-verification.md`](backup-recovery/restore-verification.md): Technical report of the isolated EBS snapshot restore test.
  - [`proof/backup-recovery/s3-daily-backup.md`](backup-recovery/s3-daily-backup.md): Automated daily KMS-encrypted PostgreSQL S3 backup specifications.
  - [`proof/cost/finops-cost-model.md`](cost/finops-cost-model.md): Detailed FinOps architecture, resource rightsizing, and cost optimization analysis.
  - [`proof/security/security-architecture.md`](security/security-architecture.md): Pod Security Standards, non-root UID 10001, and AWS KMS encryption proof.
