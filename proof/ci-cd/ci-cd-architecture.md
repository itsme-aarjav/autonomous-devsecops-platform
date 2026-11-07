# CI/CD Pipeline Architecture & GitHub Actions Engineering

## 1. Pipeline Redesign & Separation of Concerns

A critical anti-pattern in many enterprise CI/CD systems is intertwining pre-merge code validation with environment promotions. In previous iterations, a monolithic workflow contained downstream jobs gated on manual approvals for `production-promotion`, causing developer pull requests and commits to hang indefinitely in "Waiting for review" states and accumulating phantom deployment entries.

We implemented an architecture strictly decoupling **continuous integration**, **development release**, and **production promotion**:

```
.github/workflows/
├── ci.yml             # Pure validation (fmt, lint, syntax, unit tests, security scans)
├── deploy-dev.yml     # Fast, automated or dispatchable DEV release & ECR push
└── promote-prod.yml   # Explicit manual promotion gated by environment protection rules
```

---

## 2. Pipeline Inventory

### A. CI Validation Pipeline (`ci.yml`)
- **Trigger**: `push` on `main`, `pull_request` on `main`, `workflow_dispatch`
- **Concurrency**: `cancel-in-progress: true` (prevents pipeline backlog on fast commits)
- **Execution Time**: ~60-70 seconds
- **Validation Matrix (10 Jobs)**:
  1. `validate-terraform`: `terraform fmt -recursive -check devops/terraform`
  2. `validate-ansible`: `ansible-playbook --syntax-check` against all playbooks
  3. `validate-kustomize`: `kubectl kustomize` validation for base and overlays
  4. `validate-shell`: `bash -n` syntax check across all scripts
  5. `validate-aiops`: Python unit tests and security regression tests (`unittest`)
  6. `scan-trivy-fs`: Full filesystem vulnerability scan (`HIGH,CRITICAL`)
  7. `validate-boutique-containers (boutique-auth)`: Container build + Trivy scan
  8. `validate-boutique-containers (boutique-gateway)`: Container build + Trivy scan
  9. `validate-boutique-containers (boutique-frontend)`: Container build + Non-root UID 10001 assertion + Trivy scan
  10. `validate-boutique-containers (boutique-aiops-assistant)`: Container build + Trivy scan

### B. DEV Deployment Pipeline (`deploy-dev.yml`)
- **Trigger**: Manual `workflow_dispatch` with target service selection or push to DEV release tags.
- **Authentication**: Zero static secrets! Uses **GitHub OpenID Connect (OIDC)** via `aws-actions/configure-aws-credentials` assuming `arn:aws:iam::592668326948:role/github-actions-ecr-publisher`.
- **Publishing**: Builds multi-platform container images, tags with Git commit SHA and `dev-latest`, pushes to Amazon ECR, and provides immutable digests.

### C. Production Promotion Pipeline (`promote-prod.yml`)
- **Trigger**: Manual release trigger for verified stable versions.
- **Governance**: Bound to GitHub Environment `production` with required reviewer gates.

---

## 3. GitHub OIDC Hardening & IAM Trust Policy

To eliminate static `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` secrets, we established an AWS IAM OpenID Connect identity provider for `token.actions.githubusercontent.com`.

### Modern Subject Claim Matching
GitHub Actions recently updated its OIDC subject claim format to include numeric user and repository IDs alongside repository paths:
`repo:itsme-aarjav@109032559/autonomous-devsecops-platform@1447959149:ref:refs/heads/main`

To support both legacy path-only strings and modernized numeric identifiers without breaking least-privilege security, our IAM trust policy utilizes the `StringLike` operator:

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
