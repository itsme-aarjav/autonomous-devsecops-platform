# Operational Dashboards & Service Inventory

This inventory documents all live platform interfaces, remote access URLs, authentication mechanisms, and zero-trust architectural boundaries.

---

## 1. Public HTTPS Services (AWS Application Load Balancer)

All public endpoints terminate TLS using AWS Certificate Manager (ACM) RSA-2048 wildcard certificate `*.demo.aarjav.site`, routed via Route 53 to an Application Load Balancer provisioned automatically by Amazon EKS Auto Mode.

| Interface | Public URL | Ingress Port | Authentication | Verified Status |
| :--- | :--- | :--- | :--- | :--- |
| **Boutique Storefront** | [`https://demo.aarjav.site`](https://demo.aarjav.site) | 443 HTTPS | Public catalog; Authenticated demo checkout | **HTTP/2 200 OK** |
| **Grafana Visualizations** | [`https://grafana.demo.aarjav.site`](https://grafana.demo.aarjav.site) | 443 HTTPS | Native Grafana Form-Based Login & RBAC | **HTTP/2 302 &rarr; `/login`** |
| **Argo CD GitOps** | [`https://argocd.demo.aarjav.site`](https://argocd.demo.aarjav.site) | 443 HTTPS | Native Argo CD Form-Based Login & JWT Sessions | **HTTP/2 200 OK** |

---

## 2. Authentication & Credential Retrieval

### A. Pre-Seeded Recruiter Demo Account (Storefront)
The application includes a pre-registered, pre-verified recruiter demo account for testing customer workflows:

- **Email**: `recruiter@demo.aarjav.site`
- **Role**: `customer`
- **User ID**: `4808770b-1749-438b-bb5e-61d8622fcb51`
- **Password**: Securely stored in AWS Secrets Manager: `boutique/dev/recruiter-demo-credential`

To retrieve the password and authenticate via terminal:
```bash
RECRUITER_PWD=$(aws secretsmanager get-secret-value --region us-east-2 \
  --secret-id boutique/dev/recruiter-demo-credential \
  --query SecretString --output text | jq -r .password)

curl -s -X POST https://demo.aarjav.site/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"recruiter@demo.aarjav.site\",\"password\":\"${RECRUITER_PWD}\"}"
```

### B. Grafana Administrator Access
- **URL**: [`https://grafana.demo.aarjav.site`](https://grafana.demo.aarjav.site)
- **Username**: `admin`
- **Password Retrieval**:
  ```bash
  kubectl -n monitoring get secret kube-prometheus-stack-grafana \
    -o jsonpath="{.data.admin-password}" | base64 -d && echo ""
  ```

### C. Argo CD Administrator Access
- **URL**: [`https://argocd.demo.aarjav.site`](https://argocd.demo.aarjav.site)
- **Username**: `admin`
- **Password Retrieval**:
  ```bash
  kubectl -n argocd get secret argocd-initial-admin-secret \
    -o jsonpath="{.data.password}" | base64 -d && echo ""
  ```

---

## 3. Zero-Trust Internal Services (ClusterIP Only)

In adherence to zero-trust cloud architecture principles, services without native multi-user authentication mechanisms are strictly kept on internal `ClusterIP` networks. Evaluators access these securely via encrypted Kubernetes API tunnels (`kubectl port-forward`).

| Service | Internal Target | Port-Forward Command | Local URL | Zero-Trust Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Prometheus** | `svc/kube-prometheus-stack-prometheus` (`monitoring`) | `kubectl port-forward svc/kube-prometheus-stack-prometheus -n monitoring 9090:9090` | `http://localhost:9090` | Prometheus lacks native authentication. Exposing unauthenticated administrative controls to the public internet violates least-privilege security. |
| **Alertmanager** | `svc/kube-prometheus-stack-alertmanager` (`monitoring`) | `kubectl port-forward svc/kube-prometheus-stack-alertmanager -n monitoring 9093:9093` | `http://localhost:9093` | Alertmanager lacks native login. Kept internal to prevent unauthorized silence injection or routing tampering. |
| **AIOps Assistant API** | `svc/aiops-assistant` (`boutique`) | `kubectl port-forward svc/aiops-assistant -n boutique 8080:8080` | `http://localhost:8080` | Headless reasoning agent; receives alerts via SQS and internal webhook with Bearer token authentication. |
| **PostgreSQL Database** | `pod/boutique-postgres-0` (`boutique`) | `kubectl port-forward pod/boutique-postgres-0 -n boutique 5432:5432` | `localhost:5432` | Direct database access is restricted to backend microservices inside the cluster. |
