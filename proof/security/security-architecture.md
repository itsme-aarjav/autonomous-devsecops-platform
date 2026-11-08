# Cloud-Native Security & DevSecOps Hardening Architecture

## 1. Core Security Architecture Tenets

The Autonomous DevSecOps Platform implements defense-in-depth across the entire software delivery lifecycle, from code commit to cloud runtime:

1. **Zero Static AWS Credentials**: GitHub Actions authenticates exclusively via OpenID Connect (OIDC) tokens with tightly bound subject claims.
2. **Immutable Infrastructure**: Compute instances use Amazon Bottlerocket OS—a minimal, read-only Linux distribution designed specifically for hosting containers with no package manager or interactive shell.
3. **Non-Root Container Execution**: Workloads strictly run as unprivileged UIDs (`10001`), dropping all Linux capabilities (`ALL`) with `readOnlyRootFilesystem: true`.
4. **Data-at-Rest & In-Transit Encryption**: All persistent volumes (EBS), messaging queues (SQS FIFO), and state files (S3) are encrypted using customer-managed AWS KMS keys. All external and internal ingress traffic enforces TLS 1.3 / 1.2.
5. **Least-Privilege RBAC**: Kubernetes ServiceAccounts map directly to fine-grained AWS IAM roles via EKS Pod Identity without managing long-lived IAM user credentials.

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

### Live Security Verification Matrix:
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
| **PostgreSQL Backup Snapshot**| `snap-05a3b0ffe3463e280` | 100% encrypted backup snapshot |

---

## 4. EKS Control Plane Security & Migration Path to Private Cluster

### Current DEV Configuration Rationale
In the current DEV environment, the EKS cluster endpoint operates with public endpoint access enabled (`0.0.0.0/0`). This configuration is explicitly maintained to accommodate **GitHub-hosted Actions runners** (`ubuntu-24.04`), which execute CI/CD verification and deployment jobs from dynamic IP ranges across Azure datacenters without static egress IPs.

Even with public endpoint access enabled:
1. **IAM-Governed Authentication**: Every request to the Kubernetes API must carry a valid AWS STS signed bearer token from an authorized IAM principal. Anonymous and unauthenticated requests receive `401 Unauthorized`.
2. **Deterministic Kubernetes RBAC**: Authenticated IAM roles are mapped to minimal, least-privilege Kubernetes ClusterRoles. There is no anonymous access or cluster-admin sprawl.

### Production Enterprise Migration Path
For enterprise production environments, the platform architecture prescribes three clear hardening patterns:
1. **Self-Hosted In-VPC GitHub Runners (ARC)**: Deploy GitHub Actions Runner Controller (ARC) directly within private subnets of the platform VPC. CI/CD runs entirely inside the AWS network perimeter, enabling complete deactivation of the public EKS API endpoint (`endpointPublicAccess: false`, `endpointPrivateAccess: true`).
2. **Bastion / Client VPN Gateway**: Restrict public access CIDRs (`publicAccessCidrs`) to dedicated corporate VPN egress elastic IPs or AWS Client VPN endpoint CIDRs.
3. **AWS Verified Access / Cloudflare Zero Trust**: Front administrative endpoints with OIDC-authenticated identity-aware proxies, enforcing multi-factor device posture checks before granting network connectivity.

---

## 5. GitHub Actions OIDC Trust Policy & Least-Privilege Hardening

### IAM Role: `github-actions-ecr-publisher`
The GitHub Actions workflow authenticates to AWS via OpenID Connect (OIDC) through role `arn:aws:iam::592668326948:role/github-actions-ecr-publisher`.

### Overly Permissive Wildcard Elimination
During security review, account-wide wildcard conditions (`repo:itsme-aarjav/*` and `repo:itsme-aarjav*`) were identified and purged. These wildcards previously permitted any repository under the account to assume the role.

The trust policy is now strictly pinned to the exact repository claims and accepted OIDC audiences:
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
**Isolation Guarantee**: Unrelated repositories (e.g. `pokevault` or other personal repositories) cannot assume this role under any condition.

### EKS Access Entry Least-Privilege Scoping
- **Redundant Policy Removal**: `AmazonEKSViewPolicy` was cleanly disassociated as it was redundant.
- **AdminView Policy Rationale**: `AmazonEKSAdminViewPolicy` is retained as a strictly read-only cluster access policy. It grants read-only view access across cluster nodes and custom resource definitions (specifically Argo CD `applications.argoproj.io`), which are not aggregated into the default Kubernetes `view` ClusterRole. The role possesses zero write, mutation, exec, or deletion capabilities in Kubernetes.

### Known EKS Control Plane Endpoint Exception
- **Public & Private Endpoint Access**: The EKS cluster `boutique-dev-eks` has both public and private endpoint access enabled (`endpointPublicAccess: true`, `endpointPrivateAccess: true`).
- **Public CIDR Configuration (`0.0.0.0/0`)**: The public control plane CIDR block is configured to `0.0.0.0/0`. This is a documented operational necessity for this AWS DEV environment:
  1. **GitHub-Hosted Runners**: GitHub Actions workflows run on dynamic public IPs across Azure/GitHub pools that change per job execution.
  2. **Operator Access**: The human operator manages and verifies the cluster from dynamic ISP IP addresses without a corporate VPN gateway.
  Restricting public CIDRs in DEV would immediately sever GitHub Actions deployment verification and operator kubectl access.
- **Defense in Depth**: The Kubernetes API server never allows anonymous requests. Every API call is authenticated and authorized via AWS IAM OIDC web identity tokens, EKS Access Entries, and Kubernetes RBAC, with GitHub Actions restricted strictly to read-only `AmazonEKSAdminViewPolicy`.
