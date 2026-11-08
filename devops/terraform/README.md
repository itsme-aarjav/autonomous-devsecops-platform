# Terraform infrastructure

The AWS platform runs in `us-east-2` with one active environment: `production`. Existing AWS resource names may retain earlier identifiers; changing the environment label must not recreate them.

## Terraform roots

| Root | S3 state key | Purpose |
| --- | --- | --- |
| `bootstrap/` | Bootstrap state (local/S3 after initialization) | Remote state bucket |
| `persistent/` | `persistent/terraform.tfstate` | KMS, secrets, ECR, SQS, DynamoDB, S3, GitHub OIDC |
| `environments/production/` | `production/terraform.tfstate` | VPC, EKS Auto Mode and IAM |
| `environments/production/addons/` | `production/addons/terraform.tfstate` | Argo CD, Argo Rollouts and monitoring |

Shared Terraform modules live in `modules/`. The existing EKS cluster is named `boutique-dev-eks`; do not recreate it solely to rename it.

## Operations

1. Verify AWS account `592668326948` and region `us-east-2`.
2. Run `terraform init` and `terraform plan` from the intended root; inspect the plan before any apply.
3. Keep local `*.auto.tfvars`, private credentials and plan files out of Git.
4. Preserve S3 state keys, versions and backups; do not remove old state copies until recovery and state ownership have been checked separately.
5. Keep `persistent/` state and PostgreSQL backups independent of application deployments.
6. Deploy from `devops/gitops/overlays/production/` through Argo CD. AIOps remediation requires explicit human approval.

Never run an unreviewed destructive Terraform apply. Secret values must not be printed or committed.
