# AWS Cost and Teardown

The project used real AWS infrastructure for a short-lived demonstration. After saving proof of the deployment, incident recovery and database restore, the project-owned resources were intentionally removed to avoid ongoing hosting charges.

## What made the live demo expensive?

| Service | Why it cost money |
| --- | --- |
| EKS | Managed cluster control plane |
| EC2 worker nodes | Compute for Kubernetes pods |
| Application Load Balancers | HTTPS access to the storefront, Argo CD and Grafana |
| NAT Gateway and public IPv4 | Networking and outbound access |
| EBS | Database volumes and snapshots |
| Supporting services | ECR storage, KMS keys, Secrets Manager, CloudWatch and others |

Past planning reports gave different estimates for a **full month of continuous operation**, roughly `$315–$341/month` depending on assumptions. These were **run-rate estimates, not AWS invoice totals**. The demo did not necessarily run for a full month.

## Teardown result

The [teardown record](../terminal-outputs/36-aws-teardown-and-cost-elimination.txt) reports deletion of the project's EKS cluster, compute, ALBs, NAT, ECR, DynamoDB, SQS, backup bucket and other project-owned assets. The Terraform state S3 bucket was kept.

**Estimated future recurring cost attributable to this project: below $0.01/month.** This is **not a confirmed bill**. Check AWS Cost Explorer after billing data updates; earlier usage charges may still appear. Older, unrelated AWS projects are **not included** in this project's cost estimate.

The KMS key had a pending-deletion period, so its final removal is not instantaneous.

## Lessons

- For demos, collecting evidence and then deleting unused compute avoids unnecessary hourly charges.
- EKS, NAT gateways and ALBs can cost money even with little or no application traffic.
- Retained storage, keys and logs must also be checked; deleting just the cluster is not enough.
- Keep project costs separate from older account resources.
