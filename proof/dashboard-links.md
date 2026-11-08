# Operational Dashboards & Service Inventory

This inventory documents all live platform interfaces, remote access URLs, authentication mechanisms, and network security boundaries.

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

## 3. Least-Privilege Network Isolation & Cost Optimization

### Network Isolation Invariant: Why Internal Dashboards Are Kept Private
Services without native identity and access management (IAM) mechanisms (such as **Prometheus** and **Alertmanager**) are strictly isolated on internal Kubernetes `ClusterIP` networks.

Exposing unauthenticated monitoring administrative endpoints directly to the public internet presents severe attack vectors:
- **Alertmanager**: An unauthenticated attacker could inject silences, suppress critical alerts during an intrusion, or re-route telemetry.
- **Prometheus**: An attacker could craft heavy TSDB queries to cause Denial-of-Service (DoS) on monitoring nodes, or scrape sensitive environment variables and internal infrastructure topologies.

### Architectural Trade-Off: Local Port-Forwarding vs. Costly Infrastructure
In cloud environments, securing internal dashboards without port-forwarding typically requires:
1. **AWS Cognito User Pool + ALB OIDC Authentication**: Enforces OAuth2/OIDC login at the Application Load Balancer layer before traffic reaches internal pods.
2. **Dedicated Bastion Host + Multi-AZ NAT Gateways**: Incurs substantial ongoing cloud costs — each AWS NAT Gateway costs ~$32.40/month ($65–$97/month across 2–3 Availability Zones) plus $0.045/GB data processing fees, alongside Bastion EC2 compute costs.

Our platform adopts a **Private Network Isolation Model**:
- **Zero Idle Cost**: Eliminates expensive NAT Gateways and idle Bastion compute instances.
- **IAM-Governed Access**: Authorized operators tunnel directly to internal services via encrypted Kubernetes API channels (`kubectl port-forward`), authenticated through AWS IAM Signature Version 4 and Kubernetes RBAC.
- **Dual Defense**: External public access remains strictly limited to applications with mature native authentication (Grafana RBAC, Argo CD JWT sessions, Boutique Customer Auth).

| Service | Internal Target | Port-Forward Command | Local URL | Isolation Rationale |
| :--- | :--- | :--- | :--- | :--- |
| **Prometheus** | `svc/kube-prometheus-stack-prometheus` (`monitoring`) | `kubectl port-forward svc/kube-prometheus-stack-prometheus -n monitoring 9090:9090` | `http://localhost:9090` | Prometheus lacks native authentication. Kept internal to prevent TSDB DoS and infrastructure reconnaissance. |
| **Alertmanager** | `svc/kube-prometheus-stack-alertmanager` (`monitoring`) | `kubectl port-forward svc/kube-prometheus-stack-alertmanager -n monitoring 9093:9093` | `http://localhost:9093` | Alertmanager lacks native login. Kept internal to prevent unauthorized silence injection or routing tampering. |
| **AIOps Assistant API** | `svc/aiops-assistant` (`boutique`) | `kubectl port-forward svc/aiops-assistant -n boutique 8080:8080` | `http://localhost:8080` | Headless reasoning agent; receives alerts via SQS and internal webhook with Bearer token authentication. |
| **PostgreSQL Database** | `pod/boutique-postgres-0` (`boutique`) | `kubectl port-forward pod/boutique-postgres-0 -n boutique 5432:5432` | `localhost:5432` | Direct database access is restricted to backend microservices inside the cluster. |

---

## 4. Secure Operator Workstation IP Synchronization

During early development and testing, the Kubernetes API endpoint allowlist was temporarily broadened to `0.0.0.0/0`. To restore or update least-privilege `/32` IP allowlisting on demand (e.g. when the operator's dynamic ISP address changes), use the provided synchronization utility:

```bash
# Check current EKS endpoint access configuration
./scripts/operator-ip-sync.sh --status

# Automatically detect public IP and restrict EKS access to your workstation /32
./scripts/operator-ip-sync.sh

# Or specify a fixed IP explicitly
./scripts/operator-ip-sync.sh --ip 198.51.100.12
```

This updates the AWS EKS `publicAccessCidrs` in-place without touching VPC routing, destroying state, or interrupting running cluster workloads.
