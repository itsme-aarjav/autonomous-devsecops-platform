# Infrastructure as Code (Terraform)

This directory contains the Terraform configurations for the platform deployed to AWS region `us-east-2` (Ohio).

## Architecture and Directory Layout
To isolate failure domains, protect persistent state, and allow clean teardown of temporary environments, the infrastructure is split into four decoupled root modules:

```
devops/terraform/
├── bootstrap/                        # Stage 1: State storage bootstrap
│   ├── main.tf                       # S3 Remote State Bucket (AES256, versioning, TLS policy)
│   ├── variables.tf
│   ├── outputs.tf
│   └── README.md
│
├── persistent/                       # Stage 2: Persistent foundation
│   ├── provider.tf                   # Remote S3 backend (key: persistent/terraform.tfstate)
│   ├── main.tf                       # KMS CMK, Secrets Manager, ECR (4 repos: frontend, gateway, auth, aiops-assistant), SQS FIFO, DynamoDB, S3 Diagnostics
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
│
├── environments/
│   └── dev/                          # Stage 3: Development infrastructure
│       ├── provider.tf               # Remote S3 backend (key: dev/terraform.tfstate)
│       ├── main.tf                   # VPC (2 AZs), NAT Gateway, EKS Auto Mode cluster
│       ├── data.tf                   # Reads persistent state outputs
│       ├── variables.tf
│       ├── outputs.tf
│       ├── terraform.tfvars.example
│       │
│       └── addons/                   # Stage 4: Kubernetes and Helm add-ons
│           ├── provider.tf           # Remote S3 backend (key: dev/addons/terraform.tfstate)
│           ├── data.tf               # Reads Stage 3 cluster outputs
│           ├── main.tf               # Argo CD, Argo Rollouts, and Prometheus Helm releases
│           └── outputs.tf
│
└── modules/                          # Shared reusable modules
    ├── vpc/                          # 2-AZ subnets, NAT, S3 Gateway EP, ECR Interface EPs
    ├── eks/                          # EKS Auto Mode, IAM roles, Pod Identity association
    ├── ecr/                          # Microservices ECR repositories and lifecycle policies
    └── argocd/                       # Argo CD, Argo Rollouts, and kube-prometheus-stack releases
```

## Progressive Deployment Lifecycle
1. Stage 1 (Bootstrap) — Two-Phase S3 Remote State Protocol:
   - Path: `bootstrap/`
   - Target Region: `us-east-2`
   - Configures the intended target remote state S3 bucket (`boutique-aiops-tfstate-us-east-2`) with AES256 SSE, versioning, 4-flag public access block, 90-day lifecycle expiration, TLS-enforcement policy, and `prevent_destroy = true`.
   - Native S3 state locking via `use_lockfile = true` (Terraform 1.10+ native capability; DynamoDB table eliminated).
   - In a fresh AWS account, initialized with local state, planned (`terraform plan -out=bootstrap.tfplan`), applied (`terraform apply bootstrap.tfplan`), and migrated to S3 via `cp backend.tf.example backend.tf && terraform init -migrate-state`.
2. Stage 2 (Persistent) — Persistent Foundation Layer:
   - Path: `persistent/`
   - Provisions resources that outlive temporary clusters: KMS CMK (`alias/boutique-aiops-key` with `prevent_destroy = true`), AWS Secrets Manager containers (`boutique/database/credentials` and `boutique/auth/jwt-secret`), 4 ECR image repositories (boutique-frontend, boutique-gateway, boutique-auth, boutique-aiops-assistant) with KMS encryption, dedicated S3 node diagnostics bucket (`boutique-aiops-node-diagnostics-us-east-2`), SQS FIFO alert queue & DLQ (`boutique-aiops-alert-queue.fifo`), DynamoDB episode & RCA tables (`boutique-aiops-episodes`, `boutique-aiops-rca-reports`), and GitHub Actions OIDC publisher role.
   - Post-Apply Seeding: High-entropy credentials are not committed to code or state; they are seeded immediately following Stage 2 apply using the in-memory script `devops/terraform/persistent/scripts/seed_secrets.py` before Stage 3 workloads deploy.
3. Stage 3 (Dev Environment):
   - Path: `environments/dev/`
   - Provisions the network topology, security groups, and EKS 1.36 cluster with Auto Mode enabled.
4. Stage 4 (Add-ons):
   - Path: `environments/dev/addons/`
   - Connects to the active cluster and deploys Argo CD, Argo Rollouts controller & CRDs, and kube-prometheus-stack.
5. Stage 5 (GitOps Application Bootstrap):
   - Path: `devops/gitops/argo-cd.yml`
   - Once Stage 4 Helm add-ons are running and healthy, bootstrap the root Argo CD Application resource:
     ```bash
     kubectl apply -f devops/gitops/argo-cd.yml
     ```
   - This one-time declarative bootstrap connects Argo CD to `https://github.com/itsme-aarjav/autonomous-devsecops-platform.git` on branch `main`, synchronizing all manifests located in `devops/gitops/` into namespace `boutique` with automated `prune` and `selfHeal` enabled.

## Deployment Preflight Note: Scheduled KMS Key Recovery and State Alignment

> [!IMPORTANT]
> **KMS Customer Managed Key Recovery & State Alignment**:
> During the previous AWS infrastructure decommissioning phase (Stage 6.4.4), the platform KMS CMK (`alias/boutique-aiops-key`) was disassociated from its alias and scheduled for deletion with a 30-day waiting window (`PendingDeletion` status, non-billable).
> 
> When executing the final cloud deployment in this AWS account, adhere to the following preflight procedure:
> 
> 1. **Key Inspection Protocol**:
>    - `aws kms list-keys` returns only key identifiers and ARNs; it does **not** reveal key state or deletion schedules.
>    - First list candidate key IDs:
>      ```bash
>      aws kms list-keys --region us-east-2
>      ```
>    - Inspect `KeyState`, `Enabled`, `KeyManager`, and `DeletionDate` for each candidate key using `describe-key`:
>      ```bash
>      aws kms describe-key --key-id <kms-key-id> --region us-east-2
>      ```
> 
> 2. **Operator Decision & Action**:
>    - **Option 1 (Reuse Existing CMK)**:
>      - **Cancel Scheduled Deletion**: Cancelling deletion transitions the key state to `Disabled` (it does **not** re-enable the key):
>        ```bash
>        aws kms cancel-key-deletion --key-id <kms-key-id> --region us-east-2
>        ```
>      - **Enable Key**: The operator must explicitly enable the key before cryptographic operations or encryption grants can function:
>        ```bash
>        aws kms enable-key --key-id <kms-key-id> --region us-east-2
>        ```
>      - **Alias Inspection & Association**: Inspect existing aliases before attempting creation or update:
>        ```bash
>        aws kms list-aliases --region us-east-2
>        ```
>        If `alias/boutique-aiops-key` does not exist, create it:
>        ```bash
>        aws kms create-alias --alias-name alias/boutique-aiops-key --target-key-id <kms-key-id> --region us-east-2
>        ```
>        If the alias already exists but targets another key, update it:
>        ```bash
>        aws kms update-alias --alias-name alias/boutique-aiops-key --target-key-id <kms-key-id> --region us-east-2
>        ```
>      - **Terraform State Alignment Requirement**:
>        Terraform does **not** automatically discover or adopt existing AWS resources into state.
>        - If previous persistent state exists in S3 (`persistent/terraform.tfstate`) or from backup, preserve and verify that `aws_kms_key.cmk` and `aws_kms_alias.cmk_alias` match the recovered key before planning.
>        - If starting with a fresh, empty persistent state and electing to reuse the recovered CMK, the key and alias **must be imported** before executing `terraform apply`:
>          ```bash
>          cd devops/terraform/persistent
>          terraform import aws_kms_key.cmk <kms-key-id>
>          terraform import aws_kms_alias.cmk_alias alias/boutique-aiops-key
>          ```
>    - **Option 2 (Provision Fresh CMK)**:
>      - If deploying to a fresh AWS account or letting the scheduled key expire, do not cancel deletion or import.
>      - Check `aws kms list-aliases --region us-east-2` to ensure `alias/boutique-aiops-key` is not lingering on a deleted key (delete orphaned alias if necessary).
>      - Terraform will automatically provision a new KMS CMK and bind `alias/boutique-aiops-key`.
> 
> 3. **Strict Safety Guardrail**:
>    - Automation and CI/CD must **never** automatically cancel key deletions, enable keys, create/update aliases, or modify existing KMS resources without explicit operator confirmation.

## Governance and Safety Rules
- Never use `-auto-approve`: Always save plans to disk (`terraform plan -out=tfplan`) and inspect resources before applying.
- Isolation of persistent state: The `persistent/` root must not be destroyed during routine demo teardowns.
- Teardown process: Destroy temporary resources by navigating to `environments/dev/addons/` first, followed by `environments/dev/`.
- Database backup requirement: Before executing a teardown of `environments/dev/`, export PostgreSQL data using `pg_dumpall`.
