# Autonomous DevSecOps Platform — Access Inventory & Credential Guide

> **Security Notice**: This document provides connection endpoints, service topology, and command templates for evaluating the platform. In accordance with zero-trust principles, long-lived production secrets and raw tokens are **never** committed to version control.

---

## 1. Public Application Endpoint (Live DEV Demo)

The microservices boutique application is exposed via an AWS Application Load Balancer provisioned automatically by Amazon EKS Auto Mode, terminating TLS with an AWS Certificate Manager (ACM) RSA-2048 certificate.

| Attribute | Details |
| :--- | :--- |
| **Public HTTPS URL** | [`https://demo.aarjav.site`](https://demo.aarjav.site) |
| **HTTP Redirect** | `http://demo.aarjav.site` &rarr; 301 Permanent Redirect to `https://demo.aarjav.site` |
| **DNS Record** | Route 53 Alias record &rarr; `k8s-boutique-boutique-34baedbce1-932352072.us-east-2.elb.amazonaws.com` |
| **TLS Certificate** | AWS ACM: `arn:aws:acm:us-east-2:592668326948:certificate/11280403-0768-4075-b1dd-4c16e138c8ba` |
| **Status** | Verified Healthy (HTTP/2 200 OK) |

### Recruiter & Evaluator Test Account

A verified pre-seeded demo user account is available for automated and interactive testing:

| Parameter | Value | Notes |
| :--- | :--- | :--- |
| **Email** | `recruiter@demo.aarjav.site` | Pre-registered & verified in PostgreSQL 15.19 |
| **Password** | *Rotated & Encrypted in Secrets Manager* | Stored in AWS Secrets Manager: `boutique/dev/recruiter-demo-credential` |
| **User ID** | `4808770b-1749-438b-bb5e-61d8622fcb51` | UUIDv4 |
| **Role** | `customer` | Standard RBAC profile |

To retrieve the rotated password securely and authenticate via curl:
```bash
RECRUITER_PWD=$(aws secretsmanager get-secret-value --region us-east-2 \
  --secret-id boutique/dev/recruiter-demo-credential \
  --query SecretString --output text | jq -r .password)

curl -X POST https://demo.aarjav.site/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"recruiter@demo.aarjav.site\",\"password\":\"${RECRUITER_PWD}\"}"
```

---

## 2. Remote HTTPS Dashboards & Operational Interfaces

All remote services enforce HTTPS TLS encryption with AWS ACM certificates (`*.demo.aarjav.site`) and mandatory user authentication.

### A. Grafana (Observability & Metrics Visualizations)

| Attribute | Details |
| :--- | :--- |
| **Remote HTTPS URL** | [`https://grafana.demo.aarjav.site`](https://grafana.demo.aarjav.site) |
| **Authentication** | Native Grafana Form-Based Login & RBAC |
| **Default Administrator** | `admin` |
| **Admin Password Retrieval**| `kubectl -n monitoring get secret kube-prometheus-stack-grafana -o jsonpath="{.data.admin-password}" \| base64 -d` |
| **Recruiter Role** | Read-Only Viewer (can be assigned via Grafana Server Administration) |
| **Verification** | Verified Live (HTTP/2 302 &rarr; `/login`, HTTP/2 200 on login page) |

### B. Argo CD (GitOps Continuous Delivery)

| Attribute | Details |
| :--- | :--- |
| **Remote HTTPS URL** | [`https://argocd.demo.aarjav.site`](https://argocd.demo.aarjav.site) |
| **Authentication** | Native Argo CD Form-Based Login & JWT Session Management |
| **Default Administrator** | `admin` |
| **Admin Password Retrieval**| `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" \| base64 -d` |
| **Verification** | Verified Live (HTTP/2 200, `<title>Argo CD</title>`) |

### C. Prometheus (Telemetry & Scrape Engine)

| Attribute | Details |
| :--- | :--- |
| **Public Ingress Status** | **RESTRICTED / CLUSTER-INTERNAL ONLY** |
| **Security Rationale** | Prometheus does not feature native user login mechanisms. To prevent exposing unauthenticated administrative interfaces to the public internet, Prometheus is strictly kept internal. |
| **Access Method** | Encrypted Kubernetes API Port-Forwarding: `kubectl port-forward svc/kube-prometheus-stack-prometheus -n monitoring 9090:9090` &rarr; [`http://localhost:9090`](http://localhost:9090) |
| **Production SSO Prerequisite**| Exposing publicly requires an AWS Cognito User Pool with ALB OIDC action or oauth2-proxy reverse proxy. |

### D. Alertmanager (Incident Routing Engine)

| Attribute | Details |
| :--- | :--- |
| **Public Ingress Status** | **RESTRICTED / CLUSTER-INTERNAL ONLY** |
| **Security Rationale** | Alertmanager does not feature native user login mechanisms. Kept internal to prevent unauthorized silence creations or routing tampering. |
| **Access Method** | Encrypted Kubernetes API Port-Forwarding: `kubectl port-forward svc/kube-prometheus-stack-alertmanager -n monitoring 9093:9093` &rarr; [`http://localhost:9093`](http://localhost:9093) |

### E. AIOps Assistant (Autonomous SRE Reasoning Engine)

| Attribute | Details |
| :--- | :--- |
| **Service Architecture** | Headless Event-Driven FastAPI Microservice (Python 3.11) |
| **UI Dashboard** | Headless API &bull; Telemetry persisted in AWS DynamoDB tables (`boutique-aiops-rca-reports`, `boutique-aiops-episodes`) |
| **Webhook Endpoint** | `http://aiops-assistant.boutique.svc.cluster.local:8080/api/v1/alerts` (Protected via Bearer Token) |
| **Liveness / Readiness** | Port-Forward: `kubectl port-forward svc/aiops-assistant -n boutique 8080:8080` &rarr; `/health/live`, `/health/ready` |
| **Inspect RCA Reports** | `aws dynamodb scan --region us-east-2 --table-name boutique-aiops-rca-reports` |

---

## 3. Cloud Provider & Infrastructure Identity

| Scope | Identifier |
| :--- | :--- |
| **AWS Account ID** | `592668326948` |
| **Target Region** | `us-east-2` (Ohio) |
| **IAM Operator** | `arn:aws:iam::592668326948:user/terra-admin` |
| **EKS Cluster** | `boutique-dev-eks` (Kubernetes 1.36 / Bottlerocket OS / 3x `m7i-flex.large`) |
| **ECR Registry** | `592668326948.dkr.ecr.us-east-2.amazonaws.com` |
| **GitHub Actions OIDC Role** | `arn:aws:iam::592668326948:role/github-actions-ecr-publisher` |
| **AIOps Pod Identity Role** | `arn:aws:iam::592668326948:role/boutique-dev-eks-aiops-agent-role` |
| **KMS Customer Master Keys**| `bbeb7c58-6210-4ebe-8181-ce9e30b9ac7c` (EBS & DB), `1e4e2ce3-e642-47a9-a20d-3a47b052918b` (SQS FIFO), `fbae32ef-8684-4aef-83b2-722fc490f95f` (Secrets Manager & State) |
