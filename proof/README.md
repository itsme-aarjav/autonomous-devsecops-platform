# Evaluator Evidence Package

This directory contains the verified proof artifacts for the **Autonomous DevSecOps & Cloud Operations Platform**.

---

## 1. Cloud Deployment Status

The platform was historically deployed, integrated, and fully verified on AWS in account `592668326948` (region `us-east-2`) on EKS cluster `boutique-dev-eks`.

After complete end-to-end testing—including live e-commerce transactions, Prometheus incident detection, Amazon Bedrock root cause analysis, operator approval, GitOps reconciliation, and KMS database restoration—all active cloud resources were safely decommissioned.

- **Current Status**: Cloud infrastructure decommissioned to eliminate ongoing hosting costs.
- **Project Residual Cost**: Estimated at **< $0.01/month** (only the Terraform S3 state bucket < 1 MB remains, pending AWS billing confirmation).
- **Public Endpoints**: Public URLs (`demo.aarjav.site`, `argocd.demo.aarjav.site`, `grafana.demo.aarjav.site`) are no longer active.
- **Evidence Review**: Recruiters and evaluators should review the verified visual screenshots, terminal execution logs, GitHub Actions records, and technical reports cataloged below.

---

## 2. Evidence Directory Map

All evidence is organized into dedicated categories:

| Category | Description | Primary Evidence Link |
| :--- | :--- | :--- |
| **Visual Proofs** | 28 high-resolution screenshots organized across categories. | [Screenshots Index](screenshots/README.md) |
| **Execution Logs** | 36 numbered verification stages across 38 genuine terminal logs. | [Terminal Outputs Index](terminal-outputs/README.md) |
| **CI/CD & GitOps** | GitHub Actions pipeline design, ECR inventory, and 7 visual proofs. | [CI/CD Documentation](ci-cd/ci-cd-architecture.md) |
| **Observability** | Prometheus, Alertmanager, ServiceMonitors, and 11 Grafana dashboards. | [Observability Documentation](monitoring/observability-stack.md) |
| **Kubernetes Health** | Worker nodes, 26 workload pods, and 2 AWS EKS console screenshots. | [Cluster Inventory](kubernetes/cluster-inventory.md) |
| **Architecture** | Cloud topology, VPC resource map, ALBs, NAT GW, SQS, and DynamoDB. | [System Architecture](architecture/system-architecture.md) |
| **AIOps Engine** | Sequence diagram, LangGraph DAG flow, and deduplication logic. | [AIOps Pipeline](architecture/aiops-pipeline.md) |
| **Disaster Recovery** | Automated S3 SQL backup specs and isolated point-in-time restore test. | [Restore Verification](backup-recovery/restore-verification.md) |
| **Security** | Pod Security Standards, non-root UID 10001, KMS CMK, and OIDC trust. | [Security Architecture](security/security-architecture.md) |
| **FinOps Governance** | Economic analysis of operational run-rates and teardown cost verification. | [FinOps Cost Model](cost/finops-cost-model.md) |

---

## 3. Historical Verification Guides

These documents provide details on how the platform was inspected and validated during live operations:

- [Access & Service Inventory](access-inventory.md): Technical parameters of endpoints and internal service topology.
- [Dashboard & Port-Forwarding Guide](dashboard-links.md): Network isolation design and administrative tunneling.
- [Evaluator Walkthrough Guide](demo-guide.md): Historical step-by-step walkthrough of the e-commerce boutique and GitOps workflows.
- [Manual AIOps Demonstration Guide](manual-aiops-demo.md): Walkthrough of the operator CLI (`list`, `show`, `reject`, `approve`).
- [Verification Checklist](verification-checklist.md): Itemized audit checklist of verified operational capabilities.
