# Autonomous DevSecOps Platform — Evaluator & Recruiter Walkthrough Guide

Welcome to the **Autonomous DevSecOps & Cloud Operations Platform**. This guide provides an end-to-end evaluation flow designed for hiring managers, technical interviewers, and cloud architects to quickly inspect and verify the system's live capabilities.

---

## Quick Verification Checklist

- [x] **Public HTTPS Web UI**: Accessible with valid TLS at [`https://demo.aarjav.site`](https://demo.aarjav.site)
- [x] **E-Commerce Microservices**: Product catalog, real-time inventory management, transactional orders backed by PostgreSQL 15.19
- [x] **Microservices API Gateway & Auth**: Live JWT authentication and role-based access control
- [x] **Secure OIDC CI/CD Pipeline**: GitHub Actions with OpenID Connect (OIDC) & zero static AWS keys
- [x] **GitOps Continuous Delivery**: Argo CD & Argo Rollouts managing canary deployments on EKS ([`https://argocd.demo.aarjav.site`](https://argocd.demo.aarjav.site))
- [x] **Observability Stack**: Prometheus Operator, Grafana ([`https://grafana.demo.aarjav.site`](https://grafana.demo.aarjav.site)), Node Exporter, kube-state-metrics
- [x] **Autonomous AIOps Engine**: Event-driven incident triage using SQS FIFO, Amazon Bedrock, and Human-in-the-Loop PR Remediation

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

## Walkthrough Step 2: E-Commerce Catalog, Inventory & Transactional Orders

The platform features a complete PostgreSQL 15.19 e-commerce backend with atomic stock deduction, ACID transaction guarantees, and multi-tenant authorization.

### A. Inspect Live Product Catalog
Query the public catalog via the API gateway:
```bash
curl -s https://demo.aarjav.site/api/products | jq .
```
**Expected Response**:
Returns the 8 luxury boutique products seeded in PostgreSQL (*Akoya Pearl Drop Earrings*, *Cashmere Blend Overcoat*, *Classic Tailored Wool Blazer*, *Diamond Solitaire Necklace*, *Italian Leather Handbag*, *Signature Leather Wallet*, *Silk Evening Gown*, *Stiletto Designer Heels*) with real-time inventory counts and image asset paths (products are unrated by default with NULL rating in database).

### B. Verify Static Image Assets
Verify that product image assets load over HTTPS with valid content headers:
```bash
curl -I https://demo.aarjav.site/product-images/cashmere-coat.jpg
```
**Expected Response**:
```
HTTP/2 200
content-type: image/jpeg
```

### C. Place an Authenticated Demo Order (Atomic Inventory Deduction)
Authenticate as the recruiter account, retrieve a JWT Bearer token, and place a demonstration order (no real payment processed; transactional PostgreSQL deduction):
```bash
RECRUITER_PWD=$(aws secretsmanager get-secret-value --region us-east-2 \
  --secret-id boutique/dev/recruiter-demo-credential \
  --query SecretString --output text | jq -r .password)

TOKEN=$(curl -s -X POST https://demo.aarjav.site/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"recruiter@demo.aarjav.site\",\"password\":\"${RECRUITER_PWD}\"}" | jq -r .token)

# Place a demo order for 1x Cashmere Blend Overcoat (UUID: 11111111-1111-4111-8111-111111111111)
curl -s -X POST https://demo.aarjav.site/api/orders \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "shippingAddress": {
      "fullName": "Demo Recruiter",
      "addressLine1": "100 Cloud Operations Way",
      "city": "Columbus",
      "state": "OH",
      "postalCode": "43215",
      "country": "US"
    },
    "items": [
      { "productId": "11111111-1111-4111-8111-111111111111", "quantity": 1 }
    ]
  }' | jq .
```
**Expected Response**:
Order confirmation JSON with order ID, `status: "confirmed"`, calculated subtotal, 8% tax, order total, and order item breakdown.

### D. Verify Inventory Decrement & ACID Protection
Query product `10000000-0000-0000-0000-000000000001` again. Its `stock` count will have atomically decremented by 1.

Attempting to order more units than available inventory returns an immediate `400 Bad Request`:
```json
{"error": "Insufficient inventory for Cashmere Blend Overcoat. Available: X, requested: 999"}
```

### E. Verify Customer Order Ownership & Authorization
Query order history for the authenticated recruiter:
```bash
curl -s -H "Authorization: Bearer ${TOKEN}" https://demo.aarjav.site/api/orders/my-orders | jq .
```
Accessing an order with an unauthorized or unauthenticated token returns `401 Unauthorized` or `403 Forbidden`.

---

## Walkthrough Step 3: Full-Stack Authentication & API Flow

The platform includes a dedicated TypeScript authentication microservice communicating with PostgreSQL and an API Gateway reverse-proxying API traffic.

### A. Check API Health
```bash
curl -i https://demo.aarjav.site/api/auth/health
```
**Expected Response**:
```json
HTTP/2 200
content-type: application/json; charset=utf-8

{"status":"auth is healthy","timestamp":"2026-11-08T..."}
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

## Walkthrough Step 4: Observability & Telemetry

The platform runs a comprehensive Prometheus and Grafana stack on Kubernetes, secured behind AWS ACM TLS certificates and form-based authentication.

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
- **Evidence Tip**: Capture a screenshot of the live Grafana dashboard and save to `proof/screenshots/04-grafana-dashboard.png`.

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
- **Evidence Tip**: Capture a screenshot of the Argo CD application topology and save to `proof/screenshots/05-argocd-ui.png`.

### C. Internal Telemetry Engine (Prometheus & Alertmanager)
Prometheus and Alertmanager do not feature native user authentication. In compliance with network isolation standards, they are intentionally kept internal on Kubernetes `ClusterIP` to prevent exposing unauthenticated administrative endpoints:
```bash
# Secure local tunnel to Prometheus Web UI
kubectl port-forward svc/kube-prometheus-stack-prometheus -n monitoring 9090:9090
# Open http://localhost:9090 to inspect targets (100% healthy) and active alert rules

# Secure local tunnel to Alertmanager
kubectl port-forward svc/kube-prometheus-stack-alertmanager -n monitoring 9093:9093
# Open http://localhost:9093 to view routing trees and receivers
```

---

## Walkthrough Step 5: Autonomous AIOps Reasoning & Human-in-the-Loop PR

The platform features an **autonomous, event-driven site reliability agent** that triages alerts, synthesizes root-cause analysis (RCA) using Amazon Bedrock, and opens a reviewed GitHub Pull Request for human operator approval.

### Architecture Flow:
1. **Prometheus Alert**: Evaluates metrics against SLO threshold rules (e.g. `PodOOMKilled`, `ContainerRestartCrashLoop`).
2. **Alertmanager Webhook**: Signs and dispatches an authenticated HTTP POST payload to the in-cluster AIOps Assistant webhook endpoint (`/api/v1/alerts`).
3. **SQS FIFO Queue**: Decouples webhook ingress (`boutique-aiops-alert-queue.fifo`), ensuring strict message ordering, deduplication, and zero alert loss during incident bursts.
4. **Agent Worker Execution**:
   - Collects real-time diagnostic context from the Kubernetes API (`kubectl describe`, container termination reason, node conditions).
   - Scrapes Prometheus instant metrics (memory usage bytes, memory limit, host memory pressure).
5. **Amazon Bedrock Reasoning (Nova Lite)**:
   - Formulates a structured system prompt containing live diagnostic metrics, workload manifests, and host logs.
   - Generates an expert Root Cause Analysis (RCA) report with confidence scoring, blast radius analysis, and non-destructive remediation proposals.
6. **Persistence**: Stores the incident episode in DynamoDB (`boutique-aiops-episodes`) and the structured RCA report in DynamoDB (`boutique-aiops-rca-reports`).
7. **Human-in-the-Loop PR Remediation**:
   - The operator inspects proposals via `python aiops/operator_cli.py list` or `show <id>`.
   - On approval, the agent **never modifies main directly**. It creates a dedicated branch (`fix/aiops-proposal-...`) and opens a detailed GitHub Pull Request with rollback instructions and verification steps.

### Inspecting Verified Incident Records:
To inspect DynamoDB RCA reports:
```bash
aws dynamodb scan --region us-east-2 \
  --table-name boutique-aiops-rca-reports \
  --query 'Items[?attribute_exists(summary)].{Incident:incident_id.S, Category:category.S, Confidence:confidence_score.N, RootCause:root_cause.S, Recommendations:recommended_actions.L[*].S}' \
  --output table
```
- **Live Demo Instructions**: Refer to [`proof/manual-aiops-demo.md`](manual-aiops-demo.md) for the operator command sequence.

---

## Walkthrough Step 6: GitOps & CI/CD Pipeline

The platform uses **one** consolidated GitHub Actions workflow: `.github/workflows/platform.yml` (`Platform Pipeline`). It runs an automated cloud-native pipeline on pushes to `main`:

- **Automatic CI Validation**: Runs Terraform formatting, Ansible syntax checks, Kustomize validation, shell script checks, 27 AIOps regression tests, and Trivy filesystem vulnerability scans.
- **Container Build & Scan**: Builds and scans all 4 container images with Trivy (`HIGH,CRITICAL` gate) and verifies non-root execution (UID 10001).
- **ECR Publishing**: Authenticates via AWS GitHub OIDC and pushes immutable digest tags and `dev-latest` to Amazon ECR.
- **GitOps DEV Reconcile & Verify**: Automatically reconciles GitOps dev overlays with immutable digests, monitors Argo CD synchronization and Argo Rollout completion, strictly verifies replica and image parity across **every** live pod, and validates live HTTPS application health at `https://demo.aarjav.site`.
- **Production Safety** (`operation: production`): Deliberately fails closed because production infrastructure is not provisioned.

Manual runs are also available through **Actions → Platform Pipeline → Run workflow**.
