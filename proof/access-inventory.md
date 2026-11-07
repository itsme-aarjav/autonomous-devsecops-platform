# Autonomous DevSecOps Platform — Access Inventory & Credential Guide

> **Security Notice**: This document provides connection endpoints, service topology, and command templates for evaluating the platform. In accordance with zero-trust principles, long-lived production secrets and raw tokens are **never** committed to version control.

---

## 1. Public Application Endpoint (Live DEV Production-Grade Demo)

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
| **Email** | `recruiter@demo.aarjav.site` | Pre-registered & verified in PostgreSQL |
| **Password** | `SecureDemoPassword2026!` | Bcrypt salted hash stored in database |
| **User ID** | `4808770b-1749-438b-bb5e-61d8622fcb51` | UUIDv4 |
| **Role** | `customer` | Standard RBAC profile |

To test authentication via curl:
```bash
curl -X POST https://demo.aarjav.site/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"recruiter@demo.aarjav.site","password":"SecureDemoPassword2026!"}'
```

---

## 2. Protected Internal Dashboards (ClusterIP Security Posture)

All control plane and operational dashboards are intentionally isolated from the public internet using Kubernetes `ClusterIP` services. Evaluators and administrators connect securely via encrypted Kubernetes API tunnels (`kubectl port-forward`).

### A. Argo CD (GitOps Continuous Delivery)

| Attribute | Details |
| :--- | :--- |
| **Namespace / Service** | `argocd` / `argocd-server` |
| **Service Type / Port** | `ClusterIP` / 443 TCP |
| **Local Tunnel Command** | `kubectl port-forward svc/argocd-server -n argocd 8443:443` |
| **Local URL** | [`https://localhost:8443`](https://localhost:8443) |
| **Default User** | `admin` |
| **Password Retrieval** | `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" \| base64 -d` |

### B. Grafana (Observability & Metrics Visualizations)

| Attribute | Details |
| :--- | :--- |
| **Namespace / Service** | `monitoring` / `kube-prometheus-stack-grafana` |
| **Service Type / Port** | `ClusterIP` / 80 TCP |
| **Local Tunnel Command** | `kubectl port-forward svc/kube-prometheus-stack-grafana -n monitoring 3000:80` |
| **Local URL** | [`http://localhost:3000`](http://localhost:3000) |
| **Default User** | `admin` |
| **Password Retrieval** | `kubectl -n monitoring get secret kube-prometheus-stack-grafana -o jsonpath="{.data.admin-password}" \| base64 -d` |

### C. Prometheus (Telemetry & Scrape Engine)

| Attribute | Details |
| :--- | :--- |
| **Namespace / Service** | `monitoring` / `kube-prometheus-stack-prometheus` |
| **Service Type / Port** | `ClusterIP` / 9090 TCP |
| **Local Tunnel Command** | `kubectl port-forward svc/kube-prometheus-stack-prometheus -n monitoring 9090:9090` |
| **Local URL** | [`http://localhost:9090`](http://localhost:9090) |

### D. Alertmanager (Incident Routing Engine)

| Attribute | Details |
| :--- | :--- |
| **Namespace / Service** | `monitoring` / `kube-prometheus-stack-alertmanager` |
| **Service Type / Port** | `ClusterIP` / 9093 TCP |
| **Local Tunnel Command** | `kubectl port-forward svc/kube-prometheus-stack-alertmanager -n monitoring 9093:9093` |
| **Local URL** | [`http://localhost:9093`](http://localhost:9093) |

### E. AIOps Assistant (Autonomous Reasoning Engine API)

| Attribute | Details |
| :--- | :--- |
| **Namespace / Service** | `boutique` / `aiops-assistant` |
| **Service Type / Port** | `ClusterIP` / 8080 TCP |
| **Local Tunnel Command** | `kubectl port-forward svc/aiops-assistant -n boutique 8080:8080` |
| **Liveness Probe** | `curl -s http://localhost:8080/health/live` &rarr; `{"status":"ok"}` |
| **Readiness Probe** | `curl -s http://localhost:8080/health/ready` &rarr; `{"status":"ready"}` |

---

## 3. Cloud Provider & Infrastructure Identity

| Scope | Identifier |
| :--- | :--- |
| **AWS Account ID** | `592668326948` |
| **Target Region** | `us-east-2` (Ohio) |
| **IAM Operator** | `arn:aws:iam::592668326948:user/terra-admin` |
| **EKS Cluster** | `boutique-dev-eks` (Kubernetes 1.36 / Bottlerocket OS) |
| **ECR Registry** | `592668326948.dkr.ecr.us-east-2.amazonaws.com` |
| **GitHub Actions OIDC Role** | `arn:aws:iam::592668326948:role/github-actions-ecr-publisher` |
| **AIOps Pod Identity Role** | `arn:aws:iam::592668326948:role/boutique-dev-eks-aiops-agent-role` |
| **KMS Master Keys** | SQS/EBS/State: `1e4e2ce3-...`, `bbeb7c58-...` |
