# Platform Verification & Evaluation Checklist

**Status**: `READY_FOR_USER_VERIFICATION`  
**Target Environment**: AWS Account `592668326948` | Region `us-east-2` | Cluster `boutique-dev-eks`  
**Public Website**: [`https://demo.aarjav.site`](https://demo.aarjav.site)  

This checklist provides human evaluators, operators, and recruiters with an itemized verification guide to validate the entire platform.

---

## 1. E-Commerce Microservices & Data Integrity

- [x] **Relational Schema Initialized**: PostgreSQL 15 `auth_db` includes `products`, `inventory`, `orders`, and `order_items` tables with UUID primary keys and referential integrity constraints.
- [x] **Luxury Product Catalog**: 8 luxury demo products seeded with prices, descriptions, ratings, categories, and inventory counts.
- [x] **Product Catalog API**: `GET /api/products`, `GET /api/products/:id`, and `GET /api/products?search=...` verified live over HTTPS.
- [x] **Static Asset Delivery**: Luxury product images (`/product-images/*.jpg`) served with `HTTP/2 200` and `image/jpeg` content-type.
- [x] **Interactive Cart & Demo Checkout**: React UI includes full shopping cart and protected checkout flow marked clearly as `DEMO - NO REAL PAYMENT`.
- [x] **Atomic Inventory & Price Security**: `POST /api/orders` verifies real product prices from database, executes atomic `SELECT ... FOR UPDATE` inventory deductions, and rejects over-ordering attempts.
- [x] **Order Ownership Authorization**: `GET /api/orders/my-orders` returns customer's orders; cross-customer access strictly rejected with `HTTP 403 Forbidden`.

---

## 2. Remote Operational Interfaces & Dashboards

- [x] **Storefront**: [`https://demo.aarjav.site`](https://demo.aarjav.site) (HTTP/2 200 OK, ACM TLS).
- [x] **Grafana Visualizations**: [`https://grafana.demo.aarjav.site`](https://grafana.demo.aarjav.site) (HTTP/2 302 &rarr; `/login`, protected by native Grafana login).
- [x] **Argo CD GitOps UI**: [`https://argocd.demo.aarjav.site`](https://argocd.demo.aarjav.site) (HTTP/2 200 OK, protected by native Argo CD login).
- [x] **Zero-Trust Administrative Posture**: Prometheus and Alertmanager kept on internal `ClusterIP` to prevent unauthenticated internet access.

---

## 3. Autonomous AIOps & Safe Human Approval

- [x] **Safe Two-Stage Remediation**: Stage A executes autonomous Bedrock RCA and deterministic policy evaluation; Stage B strictly requires explicit human operator approval.
- [x] **Pull Request GitOps Integration**: Human approval creates a dedicated feature branch (`fix/aiops-proposal-...`) and opens a reviewed GitHub Pull Request. Direct-to-main autonomous mutations are blocked.
- [x] **Audit Trail Persistence**: Rejections and approvals atomically record operator identity, timestamps, and reasoning in DynamoDB table `boutique-aiops-rca-reports`.
- [x] **Operator CLI Verified**: `list`, `show`, `approve`, `reject`, `status` subcommands tested and fully functional in both simulation and live modes.

---

## 4. Disaster Recovery & Snapshot Restoration

- [x] **EBS Automated Snapshot**: Snapshot `snap-05a3b0ffe3463e280` completed (100% progress) and encrypted with AWS KMS CMK `bbeb7c58-6210-4ebe-8181-ce9e30b9ac7c`.
- [x] **Isolated Restoration Test**: Successfully restored into an isolated EBS volume (`vol-0e374b00d6f4cfe90`) and launched in temporary `pod/postgres-restore-verified` in `default` namespace.
- [x] **Data Integrity Validated**: PostgreSQL 15.19 started cleanly, WAL redo completed, and all historical user records (`users` table) verified intact.
- [x] **Live Database Untouched**: Production database `boutique-postgres-0` in `boutique` namespace remained active and unaltered throughout.
- [x] **Clean Resource Destruction**: Temporary pod, PVC, PV, and AWS EBS volume completely deleted after verification.

---

## 5. Security Architecture & FinOps Governance

- [x] **EKS Public API CIDR Rationale**: EKS public API `0.0.0.0/0` documented as a temporary development exception authorized in Phase 6.2E; protected by AWS IAM and Kubernetes RBAC authentication. Production route: private endpoints or bastion VPN.
- [x] **No Hardcoded Plaintext Secrets**: Zero credentials or tokens in Git repository; all demo credentials rotated and managed via AWS Secrets Manager.
- [x] **Realistic Cloud Cost Model**: Itemized run-rate of **\$341.20/month** verified across active EKS Auto Mode `m7i-flex.large` compute, ALB, NAT Gateway, EBS, and serverless pay-per-token AIOps.

---

## 6. Truthful Evaluation Evidence Framework

- [x] **Synthetic PNGs Removed**: All 11 generated screenshots removed from `proof/screenshots/`.
- [x] **Manual Capture Framework**: Directory structure prepared with `.gitkeep` and guidelines for human evaluators to save their personal screenshots and terminal logs.
