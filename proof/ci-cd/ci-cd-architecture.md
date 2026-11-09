# CI/CD Pipeline Architecture & GitHub Actions Engineering

## 1. Pipeline Overview & Separation of Concerns

A common anti-pattern in continuous integration and deployment (CI/CD) pipelines is intertwining pre-merge code validation with production promotions. Blocking PRs on manual approvals causes commits to hang indefinitely and creates phantom deployment records.

This repository uses **one consolidated GitHub Actions workflow**, `platform.yml` (`Platform Pipeline`), establishing a secure, automated end-to-end cloud-native pipeline:

```
.github/workflows/
└── platform.yml  # Automated CI -> Build & Scan -> ECR Publish -> GitOps Production Reconcile -> EKS Verification
```

---

## 2. Pipeline Execution Flow

### A. Automated End-to-End Pipeline (`platform.yml`)
- **Triggers**: Automatic `push` on `main`, `pull_request` on `main`, and manual `workflow_dispatch`.
- **Execution Flow on `main`**:
  1. **CI Validation**: Runs Terraform formatting check, Ansible playbook syntax validation, Kustomize manifest validation, shell script syntax checks, 27 AIOps unit and security regression tests, and Trivy filesystem vulnerability scanning.
  2. **Container Image Build & Scan**: Matrix build for all 4 microservices (`boutique-auth`, `boutique-gateway`, `boutique-frontend`, `boutique-aiops-assistant`), asserts non-root UID 10001 for frontend, and executes Trivy container image security scanning (`HIGH,CRITICAL` severity gate).
  3. **ECR Publishing**: Authenticates via AWS GitHub OpenID Connect (OIDC) (`arn:aws:iam::592668326948:role/github-actions-ecr-publisher`), pushes immutable commit tags and `latest` to Amazon Elastic Container Registry (ECR), and resolves immutable sha256 digests.
  4. **GitOps Production Reconciliation**: Updates `devops/gitops/overlays/production/` manifests with immutable ECR digests. Commits and pushes with `[skip ci]` when digests change to avoid infinite triggering loops.
  5. **Cluster & Workload Parity Verification**: Polls Argo CD application sync and health, verifies Frontend Argo Rollout completion (handling canary pauses), audits replica parity and running image digests across **every** running pod replica, checks restart counts, and executes live HTTPS smoke tests. *(Note: When the cluster is decommissioned or AWS deployment is disabled, this step is safely skipped without failing the pipeline).*
  6. **GitHub Deployment Record**: Creates deployment records in environment `production` only when cluster verification and smoke tests succeed, failing closed on any error.

### B. Pull Request Validation Mode
- **Trigger**: `pull_request` targeting `main`.
- **Behavior**: Executes all CI validation checks and container build/scan jobs. Skips AWS publishing, GitOps modification, and EKS verification to keep PR checks fast and secure.

---

## 3. GitHub OIDC Hardening & IAM Trust Policy

To eliminate static `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` secrets, the platform uses an AWS IAM OpenID Connect (OIDC) identity provider for `token.actions.githubusercontent.com`.

### Modern Subject Claim Matching
GitHub Actions includes numeric user and repository IDs in modern OIDC subject claims:
`repo:itsme-aarjav@109032559/autonomous-devsecops-platform@1447959149:ref:refs/heads/main`

To support both standard path strings and modern numeric identifiers without weakening least-privilege security, our IAM trust policy utilizes the `StringLike` condition operator:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::592668326948:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": [
            "repo:itsme-aarjav/autonomous-devsecops-platform:*",
            "repo:itsme-aarjav*autonomous-devsecops-platform*:ref:refs/heads/main"
          ]
        }
      }
    }
  ]
}
```

---

## 4. Visual Evidence Artifacts

The following visual proofs captured from the live environment validate this CI/CD and GitOps architecture:

1. [`02-argocd-application-overview.png`](02-argocd-application-overview.png): Master Argo CD application status (`Healthy`, `Synced` to commit `11283ea`).
2. [`03-argocd-network-topology.png`](03-argocd-network-topology.png): Live Application Load Balancer (ALB) Ingress-to-Pod network topology in Argo CD.
3. [`15-argocd-workloads-tree.png`](15-argocd-workloads-tree.png): Workload hierarchy of Deployments, ReplicaSets, and Pod instances.
4. [`16-argocd-auth-canary-gateway.png`](16-argocd-auth-canary-gateway.png): Resource views for `auth`, `gateway`, and `canary-trigger`.
5. [`17-argocd-postgres-statefulset-pvc.png`](17-argocd-postgres-statefulset-pvc.png): Database persistence tier: `boutique-postgres` StatefulSet, PVC, and Service.
6. [`18-argocd-cronjob-monitoring-ingress.png`](18-argocd-cronjob-monitoring-ingress.png): Backup CronJob, PrometheusRules, Ingress, and RBAC bindings.
7. [`24-aws-ecr-repositories.png`](24-aws-ecr-repositories.png): AWS ECR Console: 4 KMS-encrypted private container repositories.
