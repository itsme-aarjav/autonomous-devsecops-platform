# CI/CD and GitOps

The repository uses one GitHub Actions workflow: [`.github/workflows/platform.yml`](../../.github/workflows/platform.yml).

## Historical deployment flow

```text
Push to main
→ Terraform / Ansible / Kubernetes / shell validation
→ 27 AIOps unit and security tests
→ Trivy filesystem and container scans
→ Build 4 Docker images
→ Publish images to Amazon ECR
→ Update GitOps image digests
→ Argo CD sync to EKS
→ Check pods, rollout and HTTPS endpoints
```

The four images were **frontend**, **gateway**, **auth**, and **AIOps assistant**. GitHub Actions used OpenID Connect (OIDC) and a short-lived AWS role to avoid storing permanent AWS access keys.

Pull requests ran validation and build/scan checks without performing a production deployment.

## What changed after AWS teardown

The cloud environment was intentionally decommissioned. The current workflow keeps code validation, tests, builds and Trivy scanning, but **ECR publishing and the EKS deployment job are disabled**. A green current pipeline therefore proves CI health, **not a newly running AWS deployment**.

- [Workflow source](../../.github/workflows/platform.yml)
- [Historic successful live deployment](https://github.com/itsme-aarjav/autonomous-devsecops-platform/actions/runs/42529170045)
- [Historical remediation PR #2](https://github.com/itsme-aarjav/autonomous-devsecops-platform/pull/2)
- [Current workflow runs](https://github.com/itsme-aarjav/autonomous-devsecops-platform/actions)

## GitOps and rollout

Argo CD read Kubernetes manifests from Git, so deployments were reviewed and version controlled. The production frontend Argo Rollouts strategy used **50% then 100%** traffic steps with a pause. The OOMKilled **test canary** was a different workload whose memory values were changed through a reviewed PR.

## Visual evidence

- [Argo CD application](02-argocd-application-overview.png)
- [Resource tree](15-argocd-workloads-tree.png)
- [ECR repositories](24-aws-ecr-repositories.png)
