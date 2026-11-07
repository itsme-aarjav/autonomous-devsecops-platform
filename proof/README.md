# Autonomous DevSecOps & Cloud Operations Platform — Evaluator Evidence Package

> **Live Production-Grade Demo**: [`https://demo.aarjav.site`](https://demo.aarjav.site)  
> **AWS Account ID**: `592668326948` | **Region**: `us-east-2` | **Cluster**: `boutique-dev-eks`  
> **Architecture Overview**: Fully automated Infrastructure as Code, GitOps progressive delivery, zero-trust security, full observability, and an event-driven generative AI site reliability engineering (AIOps) assistant.

---

## 1. Executive Summary & Capabilities Demonstrated

This repository and evaluation package represent a complete, end-to-end implementation of modern cloud engineering, DevSecOps, and platform operations. Built to demonstrate elite engineering practices, the platform addresses real-world challenges in cloud infrastructure, CI/CD pipeline scalability, container security, and autonomous operations.

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
                             │  (Claude 3.5 Sonnet / Nova) ││   (Episodes & RCA Reports)│
                             └─────────────────────────────┘└───────────────────────────┘
```

---

## 2. Platform Highlights

| Domain | Implementation & Technology | Evidence Reference |
| :--- | :--- | :--- |
| **E-Commerce Application** | Relational products catalog, atomic inventory locking (`SELECT FOR UPDATE`), demo checkout, order history | [`proof/verification-checklist.md`](verification-checklist.md) |
| **Cloud Infrastructure** | 3-Layer Terraform (Persistent, Dev, Add-ons), AWS VPC, EKS Auto Mode, Bottlerocket OS | [`proof/architecture/system-architecture.md`](architecture/system-architecture.md) |
| **Public HTTPS Access** | AWS ACM TLS (RSA 2048), Route 53 Alias, EKS Auto Mode ALB, 100% healthy target groups | [`proof/dashboard-links.md`](dashboard-links.md) |
| **GitOps Continuous Delivery**| Argo CD 10.11.6 & Argo Rollouts 2.43.9 for canary deployments and automated rollback | [`proof/kubernetes/cluster-inventory.md`](kubernetes/cluster-inventory.md) |
| **CI/CD & OIDC Security** | GitHub Actions decoupled pipelines, GitHub OIDC (zero static AWS keys), 10/10 green checks | [`proof/ci-cd/ci-cd-architecture.md`](ci-cd/ci-cd-architecture.md) |
| **Observability & SRE** | Prometheus Operator, Grafana, Node Exporter, kube-state-metrics, custom ServiceMonitors | [`proof/monitoring/observability-stack.md`](monitoring/observability-stack.md) |
| **Autonomous AIOps Engine**| Prometheus &rarr; Alertmanager &rarr; SQS FIFO &rarr; Bedrock &rarr; DynamoDB RCA &rarr; Operator CLI PR | [`proof/manual-aiops-demo.md`](manual-aiops-demo.md) |
| **Disaster Recovery** | Verified restoration of EBS snapshot `snap-05a3b0ffe3463e280` in isolated PostgreSQL pod | [`proof/backup-recovery/restore-verification.md`](backup-recovery/restore-verification.md) |
| **DevSecOps & Hardening** | Restricted Pod Security Standards, non-root UID 10001, Trivy scanning, AWS KMS CMKs | [`proof/security/security-architecture.md`](security/security-architecture.md) |
| **FinOps Cost Governance**| Efficient single-NAT DEV topology, dynamic rightsizing, serverless pay-per-token LLM (\$341.20/mo across 3x m7i-flex.large) | [`proof/cost/finops-cost-model.md`](cost/finops-cost-model.md) |

---

## 3. Evaluation & Verification Index

Every capability is verifiable live against real AWS infrastructure:

- **Core Verification & Access**:
  - [`proof/verification-checklist.md`](verification-checklist.md): Comprehensive itemized verification checklist with `READY_FOR_USER_VERIFICATION` status.
  - [`proof/dashboard-links.md`](dashboard-links.md): Verified inventory of all public HTTPS endpoints, admin credential retrieval, and zero-trust ClusterIP rationale.
  - [`proof/manual-aiops-demo.md`](manual-aiops-demo.md): Step-by-step instructions for operators to test CLI commands (`list`, `show`, `approve`, `reject`) and trigger live incidents.
  - [`proof/backup-recovery/restore-verification.md`](backup-recovery/restore-verification.md): Technical report of the real isolated PostgreSQL EBS restore test.
  - [`proof/cost/finops-cost-model.md`](cost/finops-cost-model.md): Itemized $341.20/mo AWS FinOps economics model.

- **System Architecture**:
  - [`proof/architecture/system-architecture.md`](architecture/system-architecture.md): Complete cloud and network topology.
  - [`proof/architecture/aiops-pipeline.md`](architecture/aiops-pipeline.md): Event-driven AIOps sequence diagram, deduplication, and LLM reasoning flow.

- **CI/CD & Infrastructure Audits**:
  - [`proof/ci-cd/ci-cd-architecture.md`](ci-cd/ci-cd-architecture.md): Decoupled pipeline design and GitHub OIDC integration.
  - [`proof/ci-cd/ecr-inventory.json`](ci-cd/ecr-inventory.json): ECR image URIs, tags, and immutable SHA-256 digests.
  - [`proof/kubernetes/cluster-inventory.md`](kubernetes/cluster-inventory.md): Live node list, 24 running pods across 4 namespaces, Ingress, and PV/PVC status.
  - [`proof/monitoring/observability-stack.md`](monitoring/observability-stack.md): ServiceMonitors, Prometheus rules, and Alertmanager routing topology.
  - [`proof/security/security-architecture.md`](security/security-architecture.md): Pod Security Standards, non-root UID 10001, and AWS KMS encryption proof.

---

## 4. Immediate Live Verification Commands

Verify the live application directly from your terminal:

```bash
# 1. Test Storefront HTTPS 200 OK & TLS
curl -sI https://demo.aarjav.site | grep -E "HTTP/|date|content-type"

# 2. Query Live Products Catalog (8 seeded products)
curl -s https://demo.aarjav.site/api/products | jq '.data.total, .data.products[0].name'

# 3. Retrieve Rotated Recruiter Demo Password & Authenticate
RECRUITER_PWD=$(aws secretsmanager get-secret-value --region us-east-2 \
  --secret-id boutique/dev/recruiter-demo-credential \
  --query SecretString --output text | jq -r .password)

TOKEN=$(curl -s -X POST https://demo.aarjav.site/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"recruiter@demo.aarjav.site\",\"password\":\"${RECRUITER_PWD}\"}" | jq -r .token)

# 4. View Customer Order History
curl -s https://demo.aarjav.site/api/orders/my-orders -H "Authorization: Bearer ${TOKEN}" | jq .
```

---

## 5. Personal Evaluator Evidence Repository

Per strict platform evaluation standards, all synthetic or automatically generated screenshots have been removed.

Human evaluators and recruiters are invited to personally interact with the live platform and store their verified evidence in:
- [`proof/screenshots/`](screenshots/): Save your browser screenshots of the live storefront, checkout confirmation, Grafana, and Argo CD.
- [`proof/terminal-outputs/`](terminal-outputs/): Save command-line transcripts of your test sessions.
