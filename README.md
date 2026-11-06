# Autonomous DevSecOps & Cloud Operations Platform

[![CI](https://github.com/itsme-aarjav/autonomous-devsecops-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/itsme-aarjav/autonomous-devsecops-platform/actions/workflows/ci.yml)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-v1.36.4-326CE5.svg?logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![Argo CD](https://img.shields.io/badge/GitOps-Argo%20CD-EF7B4D.svg?logo=argo&logoColor=white)](https://argo-cd.readthedocs.io/)
[![Argo Rollouts](https://img.shields.io/badge/Progressive%20Delivery-Argo%20Rollouts-blueviolet.svg?logo=argo&logoColor=white)](https://argoproj.github.io/argo-rollouts/)
[![Ansible](https://img.shields.io/badge/Automation-Ansible%20Self--Healing-EE0000.svg?logo=ansible&logoColor=white)](https://www.ansible.com/)
[![AIOps](https://img.shields.io/badge/AIOps-LangGraph%20%2B%20Amazon%20Bedrock-232F3E.svg?logo=anthropic&logoColor=white)](https://aws.amazon.com/bedrock/)
[![Observability](https://img.shields.io/badge/Observability-Prometheus%20%2B%20Alertmanager-E6522C.svg?logo=prometheus&logoColor=white)](https://prometheus.io/)
[![Node.js](https://img.shields.io/badge/Node.js-24%20LTS-339933.svg?logo=node.js&logoColor=white)](https://nodejs.org/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL%2015-4169E1.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)

An enterprise-grade, cloud-native DevSecOps platform featuring a modern **3-Tier Microservices Architecture**, declarative GitOps driven by **Argo CD**, zero-downtime **Canary Progressive Delivery** via **Argo Rollouts**, full-stack telemetry using **Prometheus & Alertmanager**, and an intelligent **AIOps Agent (LangGraph + Claude/Bedrock)** with **Human-Approved GitOps Remediation**:
1. **Automated Root Cause Diagnosis & Policy Gating**: Deterministic LangGraph + Amazon Bedrock (Claude) diagnosis bounded by strict allowlist and resource limits.
2. **Permanent Declarative Fixes**: Authenticated **Cloud Operator Approval CLI** (`hmac.compare_digest` token auth), committing verified patches directly to GitOps manifests on `main` via atomic CAS, followed by automated Argo CD reconciliation.

---

## 1. High-Level Architecture

```mermaid
flowchart TD
    subgraph Traffic["Inbound Client Traffic"]
        User["End Users"]
    end

    subgraph Kubernetes["Kubernetes Cluster (Namespace: boutique)"]
        Ingress["Nginx / ALB Ingress Controller"]

        subgraph Canary_Delivery["Progressive Delivery (Argo Rollouts)"]
            FrontendRollout["Frontend Canary Rollout\n(React UI: 20% → 50% → 100%)"]
            FrontendActive["frontend-active (Stable)"]
            FrontendPreview["frontend-preview (Canary)"]
        end

        subgraph Core_Services["Core Microservices Tier"]
            Gateway["API Gateway\n(Express Routing & Rate Limiting)"]
            Auth["Auth Service\n(JWT Issuance & Verification)"]
            Postgres[("PostgreSQL 15 StatefulSet\n(Persistent Storage & Schemas)")]
        end

        subgraph Telemetry["Observability & Telemetry"]
            Prometheus["Prometheus Server\n(Metric Scraping & Rules)"]
            Alertmanager["Alertmanager\n(Deduplication & Webhooks)"]
        end

        subgraph AIOps_Platform["Autonomous AIOps Platform"]
            AlertQueue["Durable FIFO Alert Queue\n(Leasing & Dead Letter Queue)"]
            AIOpsAgent["AIOps Diagnostic Agent\n(8-Node LangGraph StateGraph)"]
            LLM["Amazon Bedrock / Claude Haiku\n(Prompt-Sanitized Inference)"]
            Policy["Deterministic Policy Engine\n(Allowlists & Bounded Limits)"]
        end

        subgraph Remediation["Human-Approved GitOps Remediation"]
            OperatorCLI["Cloud Operator Approval CLI\n(Constant-Time Token Auth)"]
            GitOpsRemediation["GitOps Direct Patcher\n(Declarative Permanent Fix)"]
        end
    end

    subgraph VersionControl["GitOps Repository (GitHub)"]
        GitRepo["Git Repository\n(devops/gitops/k8s/ manifests on main)"]
        ApprovalGate["Operator Bearer Token Gate\n(Constant-Time hmac.compare_digest)"]
        ArgoCD["Argo CD Controller\n(Automated Sync)"]
    end

    %% Traffic Routing
    User --> Ingress
    Ingress -->|/| FrontendActive
    Ingress -.->|Canary Weight| FrontendPreview
    FrontendRollout --> FrontendActive & FrontendPreview
    Ingress -->|/api| Gateway
    Gateway --> Auth
    Auth --> Postgres

    %% Observability Loop
    Core_Services & Canary_Delivery -->|Metrics /metrics| Prometheus
    Prometheus -->|Fires Alerts| Alertmanager
    Alertmanager -->|Webhook POST /api/v1/alerts| AlertQueue
    AlertQueue --> AIOpsAgent

    %% AIOps Investigation
    AIOpsAgent <--> LLM
    AIOpsAgent --> Policy

    %% GitOps Remediation
    Policy -->|Approved Proposal| GitOpsRemediation
    GitOpsRemediation -->|Proposes Patch| OperatorCLI
    OperatorCLI -->|Human Approval (hmac)| ApprovalGate
    ApprovalGate -->|Applies Patch to main| GitRepo
    GitRepo -.->|Synchronizes| ArgoCD
    ArgoCD -.->|Deploys to Cluster| Kubernetes
```

---

## 2. Key Architecture Pillars

### A. The 3-Tier Boutique Microservices
The platform is intentionally rationalized into an industry-standard, multi-tier microservices architecture that is robust, modular, and easy to explain:
1. **Frontend (`frontend`)**: React Single Page Application deployed with modern container standards on Node.js 24 LTS runtime.
2. **API Gateway (`gateway`)**: Central routing layer, request validation, and API aggregation point.
3. **Authentication Service (`auth`)**: Issues and validates cryptographically signed JSON Web Tokens (JWT) and manages secure user authentication.
4. **Database (`boutique-postgres`)**: PostgreSQL 15 StatefulSet with persistent volume claims, automated database restore jobs, and schema seeding.

### B. Progressive Canary Delivery with Argo Rollouts
Instead of basic Blue-Green or manual pod replacements, production traffic shifting is managed dynamically by **Argo Rollouts**:
- **Strategy**: Automated **Canary Traffic Steps**:
  - `step 1`: Route **20%** of inbound traffic to canary pod (`frontend-preview`); pause 30s.
  - `step 2`: Route **50%** of traffic to canary pod; pause 30s for health analysis.
  - `step 3`: Promote to **100%** full traffic cutover on `frontend-active`.
- **Zero Downtime**: Active traffic is continuously served while the canary version is warmed up and verified.

### C. Full-Stack Observability (Prometheus & Alertmanager)
- Real-time Prometheus metric collection across pod memory, CPU, request latency, and HTTP status codes.
- Preconfigured Alertmanager alerting rules detecting:
  - `Pod OOMKilled` (container cgroup memory exhaustion).
  - `High CPU utilization` (CPU spike exceeding thresholds).
  - `Application HTTP 5xx spike` (backend service degradation).
  - `Kubernetes Pod CrashLoopBackOff` (unhealthy pod restart loops).

### D. Autonomous In-Cluster AIOps Assistant (LangGraph DAG)
The platform features an autonomous diagnostic agent built using an **8-node LangGraph DAG**:
```
validate_input → normalize_incident → collect_evidence → sanitize_evidence → analyze_with_llm → validate_rca → propose_remediation → persist_result
```
- **Read-Only Telemetry Collection**: Strictly collects pod logs, Kubelet event streams, and PromQL metric rates without mutating cluster state.
- **Safety & Prompt Sanitization**: Redacts JWTs, database connection strings, bearer tokens, and private keys before invoking Bedrock/Claude Haiku.
- **Strict Non-Destructive Invariant**: Rejects destructive suggestions (`rm -rf`, `kubectl delete`, `DROP TABLE`).

---

## 3. Human-Approved GitOps Remediation Engine

When an incident strikes (e.g. `Pod OOMKilled` on `auth`), the platform executes a deterministic, human-gated **GitOps Remediation Workflow**:

```
Prometheus / Alertmanager Alert
       │
       ▼
AIOps LangGraph Root Cause Analysis (Amazon Bedrock Claude Haiku)
       │
       ▼
Deterministic Policy Engine Gate (Allowlist + Bounded Limits)
       │
       ▼
Cloud-Durable Proposal Store (DynamoDB: boutique-aiops-rca-reports)
       │
       ▼
Cloud Operator Approval CLI (Token-Authenticated + Diff Confirmation)
       │
       ▼
GitOps Direct-to-Main Manifest Update (Atomic CAS: PATCH refs/heads/main)
       │
       ▼
Argo CD Reconciliation & Verified Cluster Recovery
```

> [!NOTE]
> **Implementation Status & Operational Boundaries**:
> - **Human-Approved GitOps Remediation**: Core patching engine, constant-time operator authentication gate (`hmac.compare_digest`), DynamoDB proposal persistence adapter, CloudShell-ready operator approval CLI (`aiops/operator_cli.py`), and GitHub direct-main commit integration are fully coded and tested locally; live incident demonstration on AWS EKS is pending infrastructure provisioning.
> - **Ansible Scheduled Database Backups**: Ansible playbooks and tooling in `devops/ansible/` are preserved and repurposed exclusively for scheduled PostgreSQL backups in AWS (daily at 2:00 AM Asia/Kolkata), maintaining clean separation from operational cluster remediation.
> - **Amazon Bedrock Inference**: Cross-region inference profile (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) is verified active in AWS account `592668326948`; live paid inference calls will take place during the live EKS incident demonstration.

### Cloud Operator Approval Workflow
- The agent renders clean, surgical YAML diffs against the GitOps manifests in `devops/gitops/k8s/` and stores proposals in DynamoDB (`boutique-aiops-rca-reports`).
- Operators in AWS CloudShell review pending proposals, inspect diffs, and approve or reject them using the secure CLI:
  ```bash
  # List pending remediation proposals
  python3 aiops/operator_cli.py list --status pending

  # Inspect root cause, policy evaluation, and unified manifest diff
  python3 aiops/operator_cli.py show <proposal_id>

  # Authenticate with operator token and apply to main
  python3 aiops/operator_cli.py approve <proposal_id>
  ```
- Enforces **Constant-Time Human Approval Token Authentication** (`TrustedTokenApprovalAuthenticator`) using `hmac.compare_digest` against authorized operator credentials before applying remediation proposals.
- Supports deterministic proposal generation with full audit provenance (Incident ID, Episode ID, root cause diagnosis, policy verification badge, and human review checklist).
- Adheres to the platform's strict **Single-Main Branch Policy** for operational safety using atomic Compare-And-Swap GitHub branch updates.

---

## 4. Role-Based Repository Structure

```
autonomous-devsecops-platform/
├── .github/workflows/          # CI/CD pipelines (GitHub Actions)
├── application/                # Application Development (Frontend & Backend)
│   ├── backend/services/       # Node.js API Gateway & Auth microservices
│   └── frontend/               # Modern React 19 single page application
├── aiops/                      # Autonomous AIOps Agent (LangGraph + Amazon Bedrock)
│   ├── agent/                  # 8-node LangGraph DAG, schemas, runtime & remediation
│   ├── Dockerfile.agent        # Hardened non-root container image definition
│   ├── requirements-agent.txt  # Pinned agent dependencies
│   └── README.md               # AIOps architecture documentation
├── devops/                     # DevOps & Cloud Platform Operations
│   ├── ansible/                # Ansible configuration & playbooks (repurposed for cloud PostgreSQL backups)
│   │   ├── playbooks/          # Operational stabilization playbooks
│   │   ├── inventory.ini       # Local execution inventory
│   │   └── ansible.cfg         # Execution configuration
│   ├── gitops/                 # Declarative Kubernetes manifests (Kustomize & Argo CD)
│   │   ├── argo-cd.yml         # Argo CD root Application manifest
│   │   ├── kustomization.yml   # Master Kustomize root
│   │   └── k8s/                # Workload, monitoring & AIOps deployment manifests
│   ├── local/                  # Local developer stack orchestration
│   │   └── docker-compose.yml  # Self-contained local docker compose
│   ├── observability/          # Monitoring & metrics telemetry configs
│   │   ├── grafana/            # Grafana provisioning & dashboards
│   │   └── prometheus/         # Prometheus scrape configuration
│   ├── scripts/                # Platform release & image promotion utilities
│   │   ├── promote-images.sh   # ECR image promotion & GitOps updater
│   │   ├── restore-local-db.sh # Safe idempotent PostgreSQL restore
│   │   └── update_gitops_image.py # Deterministic SHA256 digest manifest updater
│   └── terraform/              # Infrastructure as code (AWS us-east-2)
│       ├── bootstrap/          # Stage 1: S3 remote state storage
│       ├── persistent/         # Stage 2: KMS CMK, ECR, SQS FIFO, DynamoDB
│       ├── environments/dev/   # Stage 3: VPC & EKS Auto Mode cluster
│       ├── modules/            # Reusable Terraform modules (vpc, eks, ecr, argocd)
│       └── scripts/            # In-memory secret seeder & JWT synchronizer
├── README.md                   # Platform documentation
├── .gitignore                  # Git path exclusions
└── .trivyignore                # Security vulnerability scanner exclusions
```

---

## 5. Local Quickstart, Building & CI Policy

The platform enforces a clear separation between **local development validation** and **GitHub Actions CI**:
- **Local Development**: Developers build containers and run validation locally. Targeted unit and security test suites are maintained for local verification and omitted from public repository distributions.
- **GitHub Actions CI**: Hosted runners execute automated formatting (Terraform fmt), syntax validation (Ansible, Shell), manifest validation (Kustomize), vulnerability scanning (Trivy filesystem and container gates), multi-stage Docker builds, and direct-to-main promotion upon human environment approval (`production-promotion`).

> [!NOTE]
> **Operational Status & Platform Readiness**:
> - **GitHub CI Validation & Multi-Stage Builds (Verified)**: Multi-stage Docker container builds (4 images), security vulnerability scanning (Trivy), Kustomize manifest validation, Ansible playbook syntax, and Terraform validation pass cleanly on hosted GitHub runners.
> - **Human-Approved GitOps Remediation**: Implemented with DynamoDB proposal persistence store, constant-time operator authentication gate (`hmac.compare_digest`), CloudShell approval CLI (`aiops/operator_cli.py`), and GitHub atomic CAS direct-main commit engine; live cluster verification pending.
> - **Ansible Scheduled Database Backups**: Tooling preserved and repurposed for automated cloud PostgreSQL backups in AWS (daily at 2:00 AM Asia/Kolkata).
> - **Amazon Bedrock (Claude Haiku 4.5)**: Cross-region inference profile (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) verified active in AWS account `592668326948`; live paid inference pending cluster deployment.
> - **Cloud & Container Infrastructure**: Terraform state bootstrap and persistent foundation configurations prepared; AWS ECR image publishing and AWS EKS Auto Mode cluster deployment pending.
> - **Local Test Suites**: Comprehensive unit and integration test suites are maintained exclusively in the local development environment and omitted from the public repository distribution.

### 1. Verify Kubernetes Manifests
```bash
kubectl kustomize devops/gitops/
```

### 2. Syntax-Check Ansible Self-Healing Playbooks
```bash
ansible-playbook -i devops/ansible/inventory.ini devops/ansible/playbooks/*.yml --syntax-check
```

### 3. Validate Terraform Formatting
```bash
terraform fmt -recursive -check devops/terraform
```

### 4. Build Microservices
```bash
# Build React 19 Frontend
cd application/frontend && npm run build

# Build Gateway and Auth Microservices
cd application/backend && npm run build
```

### 4. Optional: Run Local Development Tests (When Test Suite Is Present Locally)
```bash
# Backend security tests
cd application/backend && npm test

# Frontend unit tests
cd application/frontend && npm test

# AIOps test suite
AIOPS_BEDROCK_ENABLED="false" PYTHONPATH=aiops python3 -m unittest discover -s aiops/tests -v
```

---

## 6. The 60-Second Interview Pitch

When an interviewer asks: *"Tell me about your Autonomous DevSecOps Platform project"*, here is the concise, high-impact breakdown:

> *"I engineered a production-grade DevSecOps platform featuring a 3-tier microservices application (React 19 frontend, Node.js API Gateway, and an Auth service connected to PostgreSQL).*
> 
> *For progressive delivery, I implemented **Argo Rollouts** with an automated **Canary deployment strategy** (20% → 50% → 100% traffic shifting) alongside declarative GitOps managed by **Argo CD** on a strict **Single-Main Branch** operational model.*
> 
> *For operations and incident management, I built an in-cluster **AIOps Assistant** using **LangGraph** and **Amazon Bedrock (Claude)**. When Prometheus and Alertmanager fire an alert—such as a Pod OOMKilled—the agent gathers read-only cluster telemetry, sanitizes sensitive credentials, and performs automated root cause analysis.*
> 
> *What makes the platform unique is its **Autonomous DevSecOps & Human-Approved GitOps Remediation** workflow:
> 1. **Autonomous Root Cause Diagnosis (LangGraph + Bedrock)**: Gathers read-only cluster telemetry upon alert receipt, sanitizes sensitive tokens and URIs, performs root cause analysis with Claude, and gates proposals against a strict deterministic policy engine.
> 2. **Human-Gated GitOps Execution (Cloud Operator CLI + CAS)**: Operators review unified manifest diffs via CloudShell CLI, authenticate with constant-time tokens (`hmac.compare_digest`), and commit verified declarative fixes directly to GitOps manifests on 'main' without drift, triggering automated Argo CD sync."*
