# Historical Access & Service Inventory

This document records the endpoint specifications, authentication architecture, and network topology tested during live cloud operations.

---

## 1. Cloud Infrastructure Notice

The live AWS infrastructure has been decommissioned to eliminate ongoing cloud costs.

Public endpoints (`https://demo.aarjav.site`, `https://argocd.demo.aarjav.site`, `https://grafana.demo.aarjav.site`) are no longer active. Evaluators and recruiters should review the verified visual proofs in [`proof/screenshots/`](screenshots/README.md) and execution logs in [`proof/terminal-outputs/`](terminal-outputs/README.md).

---

## 2. Tested Endpoints & Ingress Architecture

During live testing in AWS account `592668326948` (region `us-east-2`), incoming traffic was routed through AWS Application Load Balancers provisioned automatically by EKS Auto Mode:

| Service | Historical URL | Ingress Port | TLS Certificate | Verified Outcome |
| :--- | :--- | :---: | :--- | :--- |
| **Boutique Storefront** | `https://demo.aarjav.site` | 443 | AWS ACM (RSA-2048) | HTTP 200 OK &bull; [Visual Proof](architecture/01-storefront-ui-demo.png) |
| **Argo CD GitOps** | `https://argocd.demo.aarjav.site` | 443 | AWS ACM (RSA-2048) | HTTP 200 OK &bull; [Visual Proof](ci-cd/02-argocd-application-overview.png) |
| **Grafana Observability** | `https://grafana.demo.aarjav.site` | 443 | AWS ACM (RSA-2048) | HTTP 302 &rarr; `/login` &bull; [Visual Proof](monitoring/04-grafana-cluster-compute-resources.png) |

All external HTTP traffic on port 80 automatically redirected to HTTPS port 443 with an HTTP 301 status.

---

## 3. Authentication & Credential Architecture

Security was maintained using least-privilege principles and zero static credentials in version control:

### A. Storefront Demo Customer Authentication
- **Test Identity**: `recruiter@demo.aarjav.site` pre-seeded in PostgreSQL 15.
- **Credential Storage**: Managed securely during live testing in AWS Secrets Manager (`boutique/dev/recruiter-demo-credential`).
- **Session Tokens**: Handled via cryptographically signed JSON Web Tokens (JWT) issued by the internal Auth service.

### B. Argo CD & Grafana Administrative Access
- **Argo CD**: Form-based authentication with session tokens. The initial password was stored in the Kubernetes secret `argocd-initial-admin-secret` in namespace `argocd`.
- **Grafana**: Built-in role-based access control (RBAC). The admin password was managed via the Kubernetes secret `kube-prometheus-stack-grafana` in namespace `monitoring`.

---

## 4. Internal Administrative Services (Network Isolation)

Services without mature native user authentication (such as **Prometheus** and **Alertmanager**) were strictly isolated inside the cluster:

- **Prometheus** (`port 9090`) and **Alertmanager** (`port 9093`) were kept on Kubernetes `ClusterIP` networks.
- They were never given public Ingress rules or public Load Balancer endpoints to prevent unauthenticated internet access.
- When live, operators accessed these services securely using encrypted Kubernetes API tunneling (`kubectl port-forward`).

---

## 5. Related Evidence

- [ALB Load Balancers Screenshot](architecture/22-aws-alb-load-balancers.png): Visual proof of the 3 active Application Load Balancers.
- [Storefront API Terminal Log](terminal-outputs/05-storefront-api.txt): Terminal proof of HTTPS 200 status and catalog response.
- [Observability Baseline Log](terminal-outputs/06-observability-baseline.txt): Terminal proof of healthy Prometheus targets and Grafana datasources.
