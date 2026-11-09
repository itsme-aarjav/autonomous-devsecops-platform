# Terraform Infrastructure as Code

This directory contains the Terraform configuration used to provision the platform on AWS in region `us-east-2`.

---

## 1. Modular Structure & Purpose

To reduce risk, infrastructure is split into separate layers. This separation ensures that destroying or updating compute resources does not delete persistent storage, encryption keys, or databases.

| Directory | State Key | Managed Resources |
| :--- | :--- | :--- |
| `bootstrap/` | `bootstrap/terraform.tfstate` | S3 remote state bucket and DynamoDB state lock table. |
| `persistent/` | `persistent/terraform.tfstate` | AWS KMS encryption keys, private ECR repos, DynamoDB tables, SQS FIFO queues, and GitHub OIDC role. |
| `environments/production/` | `production/terraform.tfstate` | Custom VPC (4 subnets across 2 AZs), NAT Gateway, Route Tables, and EKS Auto Mode cluster (`boutique-dev-eks`). |
| `environments/production/addons/` | `production/addons/terraform.tfstate` | Kubernetes addons including Argo CD, Argo Rollouts, and kube-prometheus-stack. |
| `modules/` | Shared | Reusable Terraform modules (`vpc`, `eks`, `ecr`, `argocd`). |

---

## 2. Why Multi-Layer Isolation Matters

1. **Blast Radius Control**: If an engineer destroys the Kubernetes cluster (`environments/production/`), the customer databases, S3 backups, and KMS keys in `persistent/` remain completely safe.
2. **State Locking**: Remote state is stored in S3 with server-side encryption and versioning enabled. DynamoDB prevents concurrent modifications.
3. **Least Privilege**: Each layer uses only the IAM permissions required for its specific resources.

---

## 3. Operational History & Current Status

- **Deployment**: The infrastructure was provisioned in AWS account `592668326948` (region `us-east-2`). The live cluster was named `boutique-dev-eks`.
- **Decommissioning**: After completing full end-to-end verification, all active cloud resources (EKS, worker nodes, ALBs, NAT Gateway, ECR repos, and DynamoDB tables) were cleanly destroyed to eliminate ongoing AWS costs.
- **Current Residual Cost**: Estimated at **< $0.01/month** (only the S3 state bucket < 1 MB remains, pending AWS billing confirmation).
- **Offline State Backups**: Exact state files from the live deployment are archived securely offline at `~/.aws/backups/autonomous-devsecops-platform/tfstate-20261109/` with permissions `600`.

---

## 4. Local Validation

To validate the Terraform manifests without connecting to AWS:

```bash
# Check formatting
terraform fmt -recursive -check .
```

---

## 5. Related Evidence

- [VPC Resource Map Screenshot](../../proof/architecture/19-aws-vpc-resource-map.png): Visual map of the 4 subnets, IGW, and NAT Gateway.
- [EKS Cluster Info Screenshot](../../proof/kubernetes/20-aws-eks-cluster-info.png): Visual proof of the live EKS Auto Mode cluster.
- [Cloud Teardown Log](../../proof/terminal-outputs/36-aws-teardown-and-cost-elimination.txt): Terminal proof of complete resource decommissioning.
- [FinOps Cost Model](../../proof/cost/finops-cost-model.md): Detailed analysis of operational run-rates and savings.
