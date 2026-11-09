# Security Controls

This document describes the security measures used in the historical AWS demo. The environment has since been decommissioned.

## Important controls

| Area | Control and purpose |
| --- | --- |
| AWS authentication | GitHub Actions used OIDC to request short-lived role credentials instead of storing long-lived AWS keys |
| Access permissions | IAM roles and Kubernetes RBAC limited access for application and operator components |
| Secrets | AWS Secrets Manager and Kubernetes Secrets stored application credentials |
| Encryption | AWS KMS was used for S3 backups and supported other encrypted project resources |
| Containers | The frontend ran as a non-root user; relevant workloads used restricted container security settings |
| Image scanning | Trivy checked the repository and Docker images for high/critical vulnerabilities in CI |
| Human approval | Operators had to review remediation proposals and diffs before creating PRs |
| Change control | GitOps used reviewed Git changes rather than allowing the AI to directly patch workloads |

## How AI-assisted fixes were controlled

1. The AIOps agent collected telemetry and removed sensitive strings before requesting a diagnosis.
2. A deterministic policy checked whether the proposed change was allowed.
3. The operator CLI checked operator identity and used a secure token comparison.
4. Approved changes opened a GitHub PR for human review and merge.
5. Argo CD reconciled the merged manifest while the cluster was active.

See [the actual approval log](../terminal-outputs/30-aiops-human-approval-pr.txt) and [PR #2](https://github.com/itsme-aarjav/autonomous-devsecops-platform/pull/2).

## Important limits

- Security controls reduce risk; they do not prove a system is perfectly secure.
- The historical EKS API/network design was not a fully private production environment.
- The isolated PostgreSQL SQL restore ran in a temporary pod using normal cluster networking, not a special air-gapped network.
- Project KMS and Secrets Manager resources were removed or scheduled for deletion during teardown.

## Evidence

- [AWS KMS screenshot](28-aws-kms-customer-managed-keys.png)
- [CI/CD design](../ci-cd/ci-cd-architecture.md)
- [Terminal verification index](../terminal-outputs/README.md)
