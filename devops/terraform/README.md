# AWS Infrastructure with Terraform

Terraform was used to create the cloud resources for this project in **AWS us-east-2**. There was **one operational production environment**. The historical EKS cluster name, `boutique-dev-eks`, was retained from earlier work.

## Configuration layout

| Root | What it managed |
| --- | --- |
| `bootstrap/` | The S3 bucket used for Terraform remote state |
| `persistent/` | KMS, Secrets Manager, ECR, SQS, DynamoDB and project storage |
| `environments/production/` | VPC, subnets, NAT Gateway, EKS and related IAM |
| `environments/production/addons/` | Kubernetes addons, including Argo CD and monitoring |
| `modules/` | Reusable infrastructure definitions |

Keeping state in separate roots helped separate application infrastructure from longer-lived services. Terraform used an **S3 remote backend with native S3 lockfiles** (`use_lockfile = true`). It did **not** rely on a new DynamoDB state-locking table.

## Current state

The live demo was intentionally torn down after verification. According to the recorded teardown:

- The production, addons and persistent state roots have no remaining managed resources.
- The **Terraform state S3 bucket** was retained.
- Four pre-teardown state snapshots were saved privately on the operator's Mac, **outside Git**.
- Project-only ongoing storage cost is estimated below `$0.01/month`, subject to AWS billing confirmation.

**Do not run `terraform apply` or `terraform destroy` to follow this documentation.** Doing so could recreate or change cloud resources. For offline formatting validation, use:

```bash
terraform fmt -recursive -check devops/terraform
```

Run that command from the repository root.

## Evidence

- [AWS VPC screenshot](../../proof/architecture/19-aws-vpc-resource-map.png)
- [EKS cluster screenshot](../../proof/kubernetes/20-aws-eks-cluster-info.png)
- [Teardown report](../../proof/terminal-outputs/36-aws-teardown-and-cost-elimination.txt)
