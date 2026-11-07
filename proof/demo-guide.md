# Autonomous DevSecOps Platform — Evaluator & Recruiter Walkthrough Guide

Welcome to the **Autonomous DevSecOps & Cloud Operations Platform**. This guide provides an end-to-end evaluation flow designed for hiring managers, technical interviewers, and cloud architects to quickly inspect and verify the system's live capabilities.

---

## Quick Verification Checklist

- [x] **Public HTTPS Web UI**: Accessible with valid TLS at [`https://demo.aarjav.site`](https://demo.aarjav.site)
- [x] **Microservices API Gateway & Auth**: Live JWT authentication backed by PostgreSQL 16
- [x] **Zero-Trust CI/CD Pipeline**: GitHub Actions with OpenID Connect (OIDC) & zero static AWS keys
- [x] **GitOps Continuous Delivery**: Argo CD & Argo Rollouts managing canary deployments on EKS
- [x] **Observability Stack**: Prometheus Operator, Grafana, Node Exporter, kube-state-metrics
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
```bash
curl -s -X POST https://demo.aarjav.site/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"recruiter@demo.aarjav.site","password":"SecureDemoPassword2026!"}'
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
  -d '{"email":"recruiter@demo.aarjav.site","password":"SecureDemoPassword2026!"}' | jq -r .token)

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

The platform runs a production-grade Prometheus and Grafana stack on Kubernetes.

### Inspect Live Metrics
Forward the Grafana port locally:
```bash
kubectl port-forward svc/kube-prometheus-stack-grafana -n monitoring 3000:80
```
Open [`http://localhost:3000`](http://localhost:3000) in your browser:
- Log in using credentials obtained via `kubectl -n monitoring get secret kube-prometheus-stack-grafana -o jsonpath="{.data.admin-password}" | base64 -d`.
- Navigate to **Dashboards** &rarr; **Kubernetes / Compute Resources / Namespace (Pods)**.
- Select namespace `boutique` to view CPU, memory, and network throughput across the microservices.

---

## Walkthrough Step 4: Autonomous AIOps Reasoning Engine

The highlight of the platform is an **autonomous, event-driven site reliability agent** that triages alerts and synthesizes root-cause analysis (RCA) using generative AI.

### Architecture Flow:
1. **Prometheus Alert**: Evaluates metrics against SLO threshold rules (e.g. `PodOOMKilled`, `ContainerRestartCrashLoop`).
2. **Alertmanager Webhook**: Signs and dispatches an authenticated HTTP POST payload to the in-cluster AIOps Assistant webhook endpoint.
3. **SQS FIFO Queue**: Decouples webhook ingress, ensuring strict message ordering, deduplication, and zero alert loss during incident bursts.
4. **Agent Worker Execution**:
   - Collects real-time diagnostic context from the Kubernetes API (`kubectl describe`, container termination reason, node conditions).
   - Scrapes Prometheus instant metrics (memory usage bytes, memory limit, host memory pressure).
5. **Amazon Bedrock Reasoning (Nova Lite)**:
   - Formulates a structured system prompt containing live diagnostic metrics, workload manifests, and host logs.
   - Generates an expert Root Cause Analysis (RCA) report with confidence scoring, blast radius analysis, and non-destructive remediation proposals.
6. **Persistence**: Stores the incident episode in DynamoDB (`boutique-aiops-episodes`) and the structured RCA report in DynamoDB (`boutique-aiops-rca-reports`).

### Inspecting Verified Incident Records:
To inspect the actual DynamoDB RCA report generated during live testing:
```bash
aws dynamodb scan --region us-east-2 \
  --table-name boutique-aiops-rca-reports \
  --query 'Items[?attribute_exists(summary)].{Incident:incident_id.S, Category:category.S, Confidence:confidence_score.N, RootCause:root_cause.S, Recommendations:recommended_actions.L[*].S}' \
  --output table
```

---

## Walkthrough Step 5: GitOps & CI/CD Pipeline

Inspect the clean, decoupled GitHub Actions workflows in `.github/workflows/`:
1. `ci.yml`: Pure validation pipeline (Terraform fmt, Ansible syntax, Kustomize manifests, Shell scripts, AIOps unit tests, Trivy FS & container security scans). Zero environment gates, passes in under 70 seconds.
2. `deploy-dev.yml`: On-demand or branch-tag release pipeline publishing multi-platform container images to Amazon ECR via GitHub OIDC without long-lived AWS secrets.
3. `promote-prod.yml`: Gated deployment workflow requiring explicit environment protection approval.

Inspect recent workflow runs:
```bash
gh run list --limit 5
```
All recent validation and DEV deployment runs show clean green passing status (`✓`).
