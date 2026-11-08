# Platform Verification & Evaluation Checklist

**Status**: `READY_FOR_USER_VERIFICATION`  
**Target Environment**: AWS Account `592668326948` | Region `us-east-2` | Cluster `boutique-dev-eks`  
**Public Website**: [`https://demo.aarjav.site`](https://demo.aarjav.site)  

This checklist provides human evaluators, operators, and recruiters with an itemized verification guide to validate the entire platform.

---

## 1. E-Commerce Microservices & Data Integrity

- [x] **Relational Schema Initialized**: PostgreSQL 15 `auth_db` includes `products`, `inventory`, `orders`, and `order_items` tables with UUID primary keys and referential integrity constraints.
- [x] **Luxury Product Catalog**: 8 luxury demo products seeded in PostgreSQL with verified prices, descriptions, categories, and inventory counts (products are unrated by default with NULL ratings in database).
- [x] **Product Catalog API**: `GET /api/products`, `GET /api/products/:id`, and `GET /api/products?search=...` verified live over HTTPS.
- [x] **Static Asset Delivery**: Luxury product images (`/product-images/*.jpg`) served with `HTTP/2 200` and `image/jpeg` content-type.
- [x] **Interactive Cart & Checkout**: React UI includes luxury boutique shopping cart and transparent demo checkout flow with clear non-payment notice and instant PostgreSQL transaction confirmation.
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
- [x] **Pull Request GitOps Integration**: Human approval creates a dedicated feature branch (`fix/aiops-proposal-...`) and opens a reviewed GitHub Pull Request with proposals bumped to 256Mi requests and 512Mi limits. Direct-to-main autonomous mutations are blocked.
- [x] **Audit Trail Persistence**: Rejections and approvals atomically record operator identity, timestamps, and reasoning in dedicated DynamoDB table `boutique-aiops-remediations` (with fallback to `boutique-aiops-rca-reports`).
- [x] **Operator CLI Verified**: `list`, `show`, `approve`, `reject`, `status` subcommands tested and fully functional in both simulation and live modes.
- [x] **GitOps DEV Promotion & Verification Workflow**: `.github/workflows/deploy-dev.yml` distinguishes read-only verification (`action: verify`, which checks desired-to-running digest parity across EVERY replica without mutation) from reviewed release promotion (`action: deploy`, which creates a GitOps PR without auto-merging and reports `AWAITING_HUMAN_REVIEW`, enforcing human review before GitOps deployment).

---

## 4. Disaster Recovery & Backup Architecture

- [x] **Real Daily PostgreSQL S3 Backup CronJob**: Two-stage Kubernetes CronJob (`postgres:15-alpine` dump + `aws-cli` upload) configured with native `timeZone: "Asia/Kolkata"` at `0 2 * * *`. Uses dedicated least-privilege `postgres-backup` ServiceAccount bound to IAM Role `boutique-dev-eks-postgres-backup-role` via EKS Pod Identity (`a-lia6abtqtjgochg8g`), isolating backup permissions from the AIOps daemon (`boutique-backup-s3-access` stripped from `boutique-dev-eks-aiops-agent-role`). Encrypted using KMS CMK (`1e4e2ce3-e642-47a9-a20d-3a47b052918b`) to S3 bucket `boutique-aiops-backups-592668326948-us-east-2/backups/`. (Scheduled 02:00 IST status: `PENDING_SCHEDULED_VERIFICATION`; verified encrypted archives present in S3).
- [x] **EBS Automated Snapshot**: Snapshot `snap-05a3b0ffe3463e280` completed (100% progress) and encrypted with AWS KMS CMK `bbeb7c58-6210-4ebe-8181-ce9e30b9ac7c`.
- [x] **Isolated Restoration Test**: Successfully restored into an isolated EBS volume (`vol-0e374b00d6f4cfe90`) and launched in temporary `pod/postgres-restore-verified` in `default` namespace.
- [x] **Data Integrity Validated**: PostgreSQL 15.19 started cleanly, WAL redo completed, and all historical user records (`users` table) verified intact.
- [x] **Live Database Untouched**: Production database `boutique-postgres-0` in `boutique` namespace remained active and unaltered throughout.
- [x] **Clean Resource Destruction**: Temporary pod, PVC, PV, and AWS EBS volume completely deleted after verification.

---

## 5. Security Architecture & FinOps Governance

- [x] **GitHub Actions OIDC IAM Hardening**: Role `github-actions-ecr-publisher` assume-role policy restricted strictly to `itsme-aarjav/autonomous-devsecops-platform:*` (`ref:refs/heads/main`, `ref:refs/tags/*`, `environment:development`). All account-wide wildcards (`repo:itsme-aarjav/*`) removed to prevent unauthorized access from other repositories (e.g. PokéVault). Redundant `AmazonEKSViewPolicy` disassociated; only read-only `AmazonEKSAdminViewPolicy` retained for node and CRD verification.
- [x] **EKS Public API CIDR Rationale**: EKS public API `0.0.0.0/0` documented as a temporary development exception authorized in Phase 6.2E; protected by AWS IAM and Kubernetes RBAC authentication. Production route: private endpoints or bastion VPN.
- [x] **No Hardcoded Plaintext Secrets**: Zero credentials or tokens in Git repository; all demo credentials rotated and managed via AWS Secrets Manager.
- [x] **Realistic Cloud Cost Model**: Itemized run-rate of **\$341.20/month** verified across active EKS Auto Mode `m7i-flex.large` compute, ALB, NAT Gateway, EBS, and serverless pay-per-token AIOps.

---

## 6. Truthful Evaluation Evidence Framework

- [x] **Synthetic Proof Removed**: All 11 generated screenshots and historical AI proofs removed from the evaluator-facing `proof/` directory.
- [x] **Manual Capture Framework**: Directory structure prepared with `.gitkeep` and guidelines for human evaluators to save their personal screenshots and terminal logs.

---

## 7. User Verification & Personal Demonstration Tasks (Pending)

The following items are strictly reserved for the human evaluator/recruiter to execute and verify personally:

- [ ] **Personal Storefront Evaluation**: Visit `https://demo.aarjav.site`, browse products, log in with demo account, place an order, and save screenshot to `proof/screenshots/01-storefront.png`.
- [ ] **Personal Grafana Verification**: Log in to `https://grafana.demo.aarjav.site`, inspect compute and pod metrics for namespace `boutique`, and save screenshot to `proof/screenshots/04-grafana-dashboard.png`.
- [ ] **Personal Argo CD Verification**: Log in to `https://argocd.demo.aarjav.site`, verify `boutique` application sync status and controller health, and save screenshot to `proof/screenshots/05-argocd-ui.png`.
- [ ] **Personal Isolated Incident Trigger**: Deploy the safe test canary workload (`devops/gitops/k8s/aiops/isolated-incident-test.yaml`) to observe real-time Alertmanager, SQS FIFO, Bedrock Nova Lite reasoning, and DynamoDB proposal creation.
- [ ] **Personal Operator CLI Evaluation**: Execute `python3 aiops/operator_cli.py list`, `show`, `reject`, and `approve`, observing Pull Request generation. Save terminal output to `proof/terminal-outputs/03-aiops-cli-session.txt`.
- [ ] **Personal PR Review & Merge**: Inspect the generated GitHub PR diff, approve and merge into `main`, and verify Argo CD automated synchronization.
