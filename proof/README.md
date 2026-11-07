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
│  (React / Non-Root UID) │                                                       │    (TypeScript / PG16)    │
└─────────────────────────┘                                                       └──────────────┬────────────┘
                                                                                                 │
                                            ┌────────────────────────────────────────────────────┴────────────┐
                                            │                                                                 │
                             ┌──────────────▼──────────────┐                                   ┌──────────────▼──────────────┐
                             │     Prometheus Operator     │                                   │    PostgreSQL 16 Database   │
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
| **Cloud Infrastructure** | 3-Layer Terraform (Persistent, Dev, Add-ons), AWS VPC, EKS Auto Mode, Bottlerocket OS | [`proof/architecture/`](architecture/system-architecture.md) |
| **Public HTTPS Access** | AWS ACM TLS (RSA 2048), Route 53 Alias, EKS Auto Mode ALB, 100% healthy target groups | [`proof/kubernetes/`](kubernetes/cluster-inventory.md) |
| **GitOps Continuous Delivery**| Argo CD 10.11.6 & Argo Rollouts 2.43.9 for canary deployments and automated rollback | [`proof/kubernetes/`](kubernetes/cluster-inventory.md) |
| **CI/CD & OIDC Security** | GitHub Actions decoupled pipelines, GitHub OIDC (zero static AWS keys), 10/10 green checks | [`proof/ci-cd/`](ci-cd/ci-cd-architecture.md) |
| **Observability & SRE** | Prometheus Operator, Grafana, Node Exporter, kube-state-metrics, custom ServiceMonitors | [`proof/monitoring/`](monitoring/observability-stack.md) |
| **Autonomous AIOps Engine**| Prometheus &rarr; Alertmanager &rarr; SQS FIFO &rarr; Bedrock Nova Lite &rarr; DynamoDB RCA reports | [`proof/aiops/`](aiops/aiops-incident-execution.md) |
| **DevSecOps & Hardening** | Restricted Pod Security Standards, non-root UID 10001, Trivy scanning, AWS KMS CMKs | [`proof/security/`](security/security-architecture.md) |
| **FinOps Cost Governance**| Efficient single-NAT DEV topology, dynamic rightsizing, serverless pay-per-token LLM (\$189.10/mo) | [`proof/cost/`](cost/finops-cost-model.md) |

---

## 3. Evidence Index & Documentation Map

Every claim in this evaluation package is supported by live data, JSON artifacts, and terminal logs:

- **Quick Start Guides**:
  - [`proof/access-inventory.md`](access-inventory.md): Public endpoints, recruiter test credentials, and protected dashboard tunneling instructions.
  - [`proof/demo-guide.md`](demo-guide.md): Step-by-step evaluator testing script covering registration, API querying, metrics, and AIOps triage.

- **System Architecture**:
  - [`proof/architecture/system-architecture.md`](architecture/system-architecture.md): Complete cloud and network topology.
  - [`proof/architecture/aiops-pipeline.md`](architecture/aiops-pipeline.md): Event-driven AIOps sequence diagram, deduplication, and LLM reasoning flow.

- **CI/CD & Deployment Records**:
  - [`proof/ci-cd/ci-cd-architecture.md`](ci-cd/ci-cd-architecture.md): Decoupled pipeline design and GitHub OIDC integration.
  - [`proof/ci-cd/ecr-inventory.json`](ci-cd/ecr-inventory.json): ECR image URIs, tags, and immutable SHA-256 digests.
  - [`proof/github-actions/clean-deployments-report.json`](github-actions/clean-deployments-report.json): GitHub deployment cleanup proof (0 remaining phantom records).
  - [`proof/github-actions/deployment-cleanup.md`](github-actions/deployment-cleanup.md): Detailed audit and resolution of the 18 stale deployment records.

- **Kubernetes & Cloud Infrastructure**:
  - [`proof/kubernetes/cluster-inventory.md`](kubernetes/cluster-inventory.md): Live node list, 24 running pods across 4 namespaces, Ingress, and PV/PVC status.

- **Monitoring & SRE**:
  - [`proof/monitoring/observability-stack.md`](monitoring/observability-stack.md): ServiceMonitors, Prometheus rules, and Alertmanager routing topology.

- **AIOps Incident Diagnostics**:
  - [`proof/aiops/aiops-incident-execution.md`](aiops/aiops-incident-execution.md): Live synthetic incident execution logs, context gathering, and reasoning metrics.
  - [`proof/aiops/rca-report-gateway-oom.json`](aiops/rca-report-gateway-oom.json): Verified DynamoDB RCA report for Gateway OOMKilled incident.
  - [`proof/aiops/rca-report-auth-oom.json`](aiops/rca-report-auth-oom.json): Verified DynamoDB RCA report for Auth OOMKilled incident.

- **Security & Compliance**:
  - [`proof/security/security-architecture.md`](security/security-architecture.md): Pod Security Standards, non-root UID 10001, and AWS KMS encryption proof.

- **FinOps & Cost Optimization**:
  - [`proof/cost/finops-cost-model.md`](cost/finops-cost-model.md): Detailed monthly run-rate model (\$189.10/mo) and architectural cost savings.

---

## 4. Immediate Live Verification

Verify the live application from any terminal:
```bash
# Test HTTPS 200 OK & TLS handshake
curl -sI https://demo.aarjav.site | grep -E "HTTP/|date|content-type"

# Test API Gateway & Auth Microservice Health
curl -s https://demo.aarjav.site/api/auth/health | jq .
```
