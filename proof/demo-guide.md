# Autonomous DevSecOps Platform — Evaluator & Recruiter Walkthrough Guide

Welcome to the **Autonomous DevSecOps & Cloud Operations Platform**. This guide provides an end-to-end evaluation flow designed for hiring managers, technical interviewers, and cloud architects to quickly inspect and verify the system's live capabilities.

---

## Quick Verification Checklist

- [x] **Public HTTPS Web UI**: Accessible with valid TLS at [`https://demo.aarjav.site`](https://demo.aarjav.site)
- [x] **Microservices API Gateway & Auth**: Live JWT authentication backed by PostgreSQL 15.19
- [x] **Zero-Trust CI/CD Pipeline**: GitHub Actions with OpenID Connect (OIDC) & zero static AWS keys
- [x] **GitOps Continuous Delivery**: Argo CD & Argo Rollouts managing canary deployments on EKS ([`https://argocd.demo.aarjav.site`](https://argocd.demo.aarjav.site))
- [x] **Observability Stack**: Prometheus Operator, Grafana ([`https://grafana.demo.aarjav.site`](https://grafana.demo.aarjav.site)), Node Exporter, kube-state-metrics
- [x] **Autonomous AIOps Engine**: Event-driven incident triage using SQS FIFO & Amazon Bedrock (Nova Lite)

---

## Walkthrough Step 1: Public Web Store Verification

1. Open your browser and navigate to:
   ```
   https://demo.aarjav.site
   ```
2. Verify security attributes:
   - Notice the green padlock in your browser URL bar.
   - Click the lock icon to view the TLS certificate issued by **Amazon** for `demo.aarjav.site`.
   - Test plain HTTP redirect: navigate to `http://demo.aarjav.site` and observe the immediate `301 Moved Permanently` redirect to HTTPS.

---

## Walkthrough Step 2: Full-Stack Authentication & API Flow

The platform includes a dedicated TypeScript authentication microservice communicating with PostgreSQL and an API Gateway reverse-proxying API traffic.

### A. Check API Health
```bash
curl -i https://demo.aarjav.site/api/auth/health
```
**Expected Response**:
```json
HTTP/2 200
content-type: application/json; charset=utf-8

{"status":"auth is healthy","timestamp":"2026-11-07T..."}
```

### B. Authenticate as Recruiter Demo Account
Retrieve the rotated password from AWS Secrets Manager:
```bash
RECRUITER_PWD=$(aws secretsmanager get-secret-value --region us-east-2 \
  --secret-id boutique/dev/recruiter-demo-credential \
  --query SecretString --output text | jq -r .password)

curl -s -X POST https://demo.aarjav.site/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"recruiter@demo.aarjav.site\",\"password\":\"${RECRUITER_PWD}\"}"
```
**Expected Response**:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "id": "4808770b-1749-438b-bb5e-61d8622fcb51",
    "email": "recruiter@demo.aarjav.site",
    "role": "customer"
  }
}
```

### C. Verify Authorized Route via Signed Bearer Token
Extract the JWT token from the login response and call `/api/auth/me`:
```bash
TOKEN=$(curl -s -X POST https://demo.aarjav.site/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"recruiter@demo.aarjav.site\",\"password\":\"${RECRUITER_PWD}\"}" | jq -r .token)

curl -s -H "Authorization: Bearer ${TOKEN}" https://demo.aarjav.site/api/auth/me | jq .
```
**Expected Response**:
```json
{
  "id": "4808770b-1749-438b-bb5e-61d8622fcb51",
  "email": "recruiter@demo.aarjav.site",
  "firstName": "Demo",
  "lastName": "Recruiter",
  "role": "customer"
}
```

---

## Walkthrough Step 3: Observability & Telemetry

The platform runs a production-grade Prometheus and Grafana stack on Kubernetes, secured behind AWS ACM TLS certificates and form-based authentication.

### A. Grafana Remote Dashboards
Navigate directly to the remote Grafana interface in your browser:
```
https://grafana.demo.aarjav.site
```
- **Login Credentials**:
  - Username: `admin`
  - Retrieve password:
    ```bash
    kubectl -n monitoring get secret kube-prometheus-stack-grafana -o jsonpath="{.data.admin-password}" | base64 -d
    ```
- **Recommended Dashboards**:
  - Navigate to **Dashboards** &rarr; **Kubernetes / Compute Resources / Namespace (Pods)**.
  - Select namespace `boutique` to view CPU, memory, and network throughput across all active microservices.
- **Evidence Screenshot**: Refer to [`proof/screenshots/02-grafana-login.png`](screenshots/02-grafana-login.png) for the live TLS login prompt.

### B. Argo CD GitOps Continuous Delivery
Navigate to the remote Argo CD interface:
```
https://argocd.demo.aarjav.site
```
- **Login Credentials**:
  - Username: `admin`
  - Retrieve password:
    ```bash
    kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
    ```
- **Live Status**: Inspect the `boutique-dev` application and healthy Argo Rollouts canary controllers.
- **Evidence Screenshot**: Refer to [`proof/screenshots/03-argocd-login.png`](screenshots/03-argocd-login.png) and [`proof/screenshots/11-argocd-and-rollouts-controllers.png`](screenshots/11-argocd-and-rollouts-controllers.png).

### C. Zero-Trust Telemetry Engine (Prometheus & Alertmanager)
Prometheus and Alertmanager do not feature native user authentication. In compliance with strict zero-trust standards, they are intentionally kept internal on Kubernetes `ClusterIP` to prevent exposing unauthenticated administrative endpoints:
```bash
# Secure local tunnel to Prometheus Web UI
kubectl port-forward svc/kube-prometheus-stack-prometheus -n monitoring 9090:9090
# Open http://localhost:9090 to inspect targets (100% healthy) and active alert rules

# Secure local tunnel to Alertmanager
kubectl port-forward svc/kube-prometheus-stack-alertmanager -n monitoring 9093:9093
# Open http://localhost:9093 to view routing trees and receivers
```
- **Evidence Screenshot**: Refer to [`proof/screenshots/08-prometheus-targets-and-rules.png`](screenshots/08-prometheus-targets-and-rules.png).

---

## Walkthrough Step 4: Autonomous AIOps Reasoning Engine

The highlight of the platform is an **autonomous, event-driven site reliability agent** that triages alerts and synthesizes root-cause analysis (RCA) using generative AI.

### Architecture Flow:
1. **Prometheus Alert**: Evaluates metrics against SLO threshold rules (e.g. `PodOOMKilled`, `ContainerRestartCrashLoop`).
2. **Alertmanager Webhook**: Signs and dispatches an authenticated HTTP POST payload to the in-cluster AIOps Assistant webhook endpoint (`/api/v1/alerts`).
3. **SQS FIFO Queue**: Decouples webhook ingress (`boutique-aiops-alert-queue.fifo`), ensuring strict message ordering, deduplication, and zero alert loss during incident bursts.
4. **Agent Worker Execution**:
   - Collects real-time diagnostic context from the Kubernetes API (`kubectl describe`, container termination reason, node conditions).
   - Scrapes Prometheus instant metrics (memory usage bytes, memory limit, host memory pressure).
5. **Amazon Bedrock Reasoning (Nova Lite)**:
   - Formulates a structured system prompt containing live diagnostic metrics, workload manifests, and host logs.
   - Generates an expert Root Cause Analysis (RCA) report with confidence scoring, blast radius analysis, and non-destructive remediation proposals in under 4 seconds.
6. **Persistence**: Stores the incident episode in DynamoDB (`boutique-aiops-episodes`) and the structured RCA report in DynamoDB (`boutique-aiops-rca-reports`).

### Inspecting Verified Incident Records:
To inspect the actual DynamoDB RCA reports generated during live testing:
```bash
aws dynamodb scan --region us-east-2 \
  --table-name boutique-aiops-rca-reports \
  --query 'Items[?attribute_exists(summary)].{Incident:incident_id.S, Category:category.S, Confidence:confidence_score.N, RootCause:root_cause.S, Recommendations:recommended_actions.L[*].S}' \
  --output table
```
- **Evidence Screenshot**: Refer to [`proof/screenshots/09-aiops-incident-rca.png`](screenshots/09-aiops-incident-rca.png) and [`proof/screenshots/10-aws-architecture-security.png`](screenshots/10-aws-architecture-security.png).

---

## Walkthrough Step 5: GitOps & CI/CD Pipeline

The platform uses decoupled, single-responsibility GitHub Actions workflows:

1. **`ci.yml` (Pre-Merge Validation)**:
   - 10 parallel linting and security scans: Terraform fmt/validate, Ansible lint, Shellcheck, Kustomize dry-run, Python/TypeScript tests, Trivy vulnerability scans.
   - Runs in ~60 seconds with strict branch concurrency (`cancel-in-progress` enabled for PRs, disabled for `main`).
   - Zero AWS permissions required.
2. **`publish-ecr.yml` (Container Build & Release)**:
   - Triggered on tags or manual dispatch.
   - Assumes AWS IAM role via GitHub OIDC (`arn:aws:iam::592668326948:role/github-actions-ecr-publisher`).
   - Builds multi-platform container images, performs Trivy vulnerability scanning, and publishes immutable image digests (`sha256:...`) to Amazon ECR.
3. **`deploy-dev.yml` (GitOps Deployment & Live Verification)**:
   - Synchronizes Kubernetes manifests to Amazon EKS DEV cluster.
   - Records genuine GitHub Deployment events (`environment: development`, tracking statuses: `in_progress`, `success`, `failure`).
   - Executes live post-deployment HTTP smoke tests against `https://demo.aarjav.site`.
4. **`promote-prod.yml` (Production Gate - Fails Closed)**:
   - Strictly fails-closed (`exit 1`) with an explicit alert indicating production infrastructure is NOT provisioned. Never reports false green.

- **Evidence Screenshot**: Refer to [`proof/screenshots/05-github-ci-checks.png`](screenshots/05-github-ci-checks.png), [`proof/screenshots/06-eks-cluster-workloads.png`](screenshots/06-eks-cluster-workloads.png), and [`proof/screenshots/07-ecr-image-digests.png`](screenshots/07-ecr-image-digests.png).
