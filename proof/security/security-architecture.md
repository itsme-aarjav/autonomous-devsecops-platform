# Cloud-Native Security & DevSecOps Hardening Architecture

## 1. Core Security Tenets

The Autonomous DevSecOps Platform implements defense-in-depth across the entire software delivery lifecycle, from code commit to cloud runtime:

1. **Zero Static AWS Credentials**: GitHub Actions authenticates exclusively via OpenID Connect (OIDC) web identity tokens with tightly scoped repository claims.
2. **Immutable Infrastructure**: Compute instances use Amazon Bottlerocket OS—a security-hardened Linux distribution built specifically for containers, with a read-only root filesystem and no package manager or interactive shell.
3. **Non-Root Container Execution**: Application containers run as unprivileged UID `10001`, dropping all Linux capabilities (`ALL`) with `readOnlyRootFilesystem: true`.
4. **Data Encryption at Rest and in Transit**: Persistent volumes (EBS), incident message queues (SQS FIFO), container images (ECR), and Terraform states (S3) are encrypted using AWS KMS Customer Managed Keys. External and internal ingress traffic enforces TLS 1.3 / 1.2.
5. **Least-Privilege RBAC & IAM**: Kubernetes ServiceAccounts map directly to fine-grained AWS IAM roles via EKS Pod Identity without long-lived IAM user access keys.
6. **Constant-Time HMAC Operator Authentication**: Remediation approvals in the CLI are protected by constant-time HMAC token validation (`hmac.compare_digest`) to prevent timing attacks.

---

## 2. Pod Security Standards (Restricted Profile)

The following manifest excerpt from `boutique-aiops-assistant` and `boutique-frontend` illustrates adherence to Kubernetes Restricted Pod Security Standards:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  runAsGroup: 10001
  fsGroup: 10001
  seccompProfile:
    type: RuntimeDefault
containers:
  - name: aiops-agent
    securityContext:
      allowPrivilegeEscalation: false
      readOnlyRootFilesystem: true
      capabilities:
        drop:
          - ALL
```

### Security Posture Matrix:
| Pod | ServiceAccount | RunAsNonRoot | UID | Read-Only FS | Capabilities Dropped |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `frontend` | `default` | Yes | 10001 | Yes | ALL |
| `aiops-assistant` | `aiops-assistant` | Yes | 10001 | Yes | ALL |
| `auth` | `default` | Yes | Non-Root | Yes | System defaults |
| `gateway` | `default` | Yes | Non-Root | Yes | System defaults |

---

## 3. Cryptographic Key Management (AWS KMS)

All sensitive data stores are encrypted at rest using dedicated AWS Key Management Service (KMS) Customer Managed Keys (CMKs):

| Resource | KMS Key ARN | Purpose |
| :--- | :--- | :--- |
| **PostgreSQL EBS Volume** | `arn:aws:kms:us-east-2:592668326948:key/bbeb7c58-6210-4ebe-8181-ce9e30b9ac7c` | Database volume encryption (`gp3`) |
| **SQS FIFO Alert Queue** | `arn:aws:kms:us-east-2:592668326948:key/1e4e2ce3-e642-47a9-a20d-3a47b052918b` | Telemetry message encryption |
| **Secrets Manager** | `arn:aws:kms:us-east-2:592668326948:key/bbeb7c58-6210-4ebe-8181-ce9e30b9ac7c` | Webhook tokens and DB credentials |
| **PostgreSQL Backup Snapshot**| `snap-05a3b0ffe3463e280` | Encrypted automated EBS snapshot |
| **PostgreSQL S3 Backup** | `arn:aws:kms:us-east-2:592668326948:key/1e4e2ce3-e642-47a9-a20d-3a47b052918b` | Daily compressed SQL backup in S3 |

---

## 4. EKS Control Plane Security & Migration Path to Private Cluster

### Development Endpoint Rationale
In the development environment, the EKS cluster endpoint had public access enabled (`0.0.0.0/0`). This configuration accommodated **GitHub-hosted Actions runners** (`ubuntu-24.04`), which execute CI/CD verification and deployment jobs from dynamic IP pools without static egress IPs.

Even with public endpoint access enabled:
1. **IAM-Governed Authentication**: Every API request must carry a valid AWS STS signed bearer token from an authorized IAM principal. Anonymous and unauthenticated requests receive `401 Unauthorized`.
2. **Kubernetes RBAC**: Authenticated IAM roles are mapped to minimal, least-privilege Kubernetes ClusterRoles.

### Production Enterprise Migration Path
For enterprise production environments, the platform prescribes three hardening paths:
1. **Self-Hosted In-VPC GitHub Runners (ARC)**: Deploy Actions Runner Controller (ARC) directly within private VPC subnets, allowing public EKS endpoints to be completely disabled (`endpointPublicAccess: false`, `endpointPrivateAccess: true`).
2. **Bastion / Client VPN Gateway**: Restrict public CIDRs (`publicAccessCidrs`) to dedicated corporate VPN egress Elastic IPs.
3. **AWS Verified Access / Zero Trust Proxy**: Front administrative endpoints with OIDC-authenticated identity-aware proxies enforcing device posture checks.

---

## 5. GitHub Actions OIDC Trust Policy & Hardening

### IAM Role: `github-actions-ecr-publisher`
The GitHub Actions workflow authenticates to AWS via OpenID Connect (OIDC) through role `arn:aws:iam::592668326948:role/github-actions-ecr-publisher`.

### Elimination of Overly Permissive Wildcards
During security review, account-wide wildcard conditions (`repo:itsme-aarjav/*`) were identified and eliminated. The trust policy is strictly pinned to the exact repository:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::592668326948:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": [
            "sts.amazonaws.com",
            "https://github.com/itsme-aarjav"
          ]
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": [
            "repo:itsme-aarjav/autonomous-devsecops-platform:*",
            "repo:itsme-aarjav@*/autonomous-devsecops-platform@*:*"
          ]
        }
      }
    }
  ]
}
```
**Isolation Guarantee**: Unrelated repositories cannot assume this role under any condition.

---

## 6. Visual Cryptographic Proof

1. [`28-aws-kms-customer-managed-keys.png`](28-aws-kms-customer-managed-keys.png): AWS KMS Console showing Customer Managed Key `1e4e2ce3-e642-47a9-a20d-3a47b052918b` (alias `boutique-aiops-key`), Enabled, Symmetric, providing envelope encryption for S3 backups, SQS FIFO queues, and ECR repositories.
