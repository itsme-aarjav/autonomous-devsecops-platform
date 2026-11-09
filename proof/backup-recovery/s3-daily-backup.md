# Daily PostgreSQL S3 Backup Architecture

> **Target Environment**: AWS Account `592668326948` | Region `us-east-2` | Cluster `boutique-dev-eks`
> **S3 Backup Destination**: `s3://boutique-aiops-backups-592668326948-us-east-2/backups/`
> **AWS KMS Key ID**: `1e4e2ce3-e642-47a9-a20d-3a47b052918b`
> **Kubernetes CronJob**: `postgres-backup-daily` in namespace `boutique`
> **Schedule**: Daily at 02:00 AM IST (`schedule: "0 2 * * *"`, `timeZone: "Asia/Kolkata"`)

---

## 1. Architectural Overview

The database backup pipeline uses a decoupled, two-stage Kubernetes CronJob pod architecture:

```
┌────────────────────────────────────────────────────────────────────────┐
│               Kubernetes CronJob: postgres-backup-daily                │
├───────────────────────────────────┬────────────────────────────────────┤
│ Stage 1: initContainer            │ Stage 2: container                 │
│ Image: postgres:15-alpine         │ Image: public.ecr.aws/aws-cli      │
├───────────────────────────────────┼────────────────────────────────────┤
│ 1. Connects to internal DB        │ 1. Inherits shared volume /backup  │
│    (boutique-postgres:5432)       │ 2. Reads SQL gzip archive          │
│ 2. Executes pg_dump               │ 3. Executes aws s3 cp with:        │
│ 3. Compresses with gzip -9        │    --sse aws:kms                   │
│ 4. Verifies size (> 500 bytes)    │    --sse-kms-key-id <kms-key-id>   │
│ 5. Validates gzip integrity (-t)  │ 4. Executes aws s3api head-object  │
│ 6. Writes to shared /backup       │    verifying SSE is aws:kms & key  │
└───────────────────────────────────┴────────────────────────────────────┘
```

---

## 2. Security, EKS Pod Identity, and Least-Privilege Architecture

### Dedicated ServiceAccount & EKS Pod Identity
The CronJob uses a dedicated least-privilege `postgres-backup` ServiceAccount bound to IAM Role `boutique-dev-eks-postgres-backup-role` via **EKS Pod Identity**:
- **Cluster**: `boutique-dev-eks`
- **Namespace**: `boutique`
- **ServiceAccount**: `postgres-backup`
- **Association ID**: `a-lia6abtqtjgochg8g`
- **Role ARN**: `arn:aws:iam::592668326948:role/boutique-dev-eks-postgres-backup-role`

### Least-Privilege IAM Separation
To prevent privilege sprawl:
1. `aiops-assistant` ServiceAccount retains only policies needed for Bedrock inference, SQS messaging, DynamoDB state tracking, and read-only diagnostics. All S3 database backup permissions (`boutique-backup-s3-access`) were removed from `boutique-dev-eks-aiops-agent-role`.
2. `postgres-backup` ServiceAccount is isolated to `boutique-dev-eks-postgres-backup-role`, containing only S3 backup bucket write access and KMS key encrypt/decrypt permissions.

Attached IAM Policy (`boutique-postgres-backup-policy` on `boutique-dev-eks-postgres-backup-role`):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PostgresBackupS3Access",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::boutique-aiops-backups-592668326948-us-east-2",
        "arn:aws:s3:::boutique-aiops-backups-592668326948-us-east-2/backups/*"
      ]
    },
    {
      "Sid": "PostgresBackupKMSAccess",
      "Effect": "Allow",
      "Action": [
        "kms:GenerateDataKey",
        "kms:Decrypt",
        "kms:DescribeKey"
      ],
      "Resource": "arn:aws:kms:us-east-2:592668326948:key/1e4e2ce3-e642-47a9-a20d-3a47b052918b"
    }
  ]
}
```

---

## 3. Manual Operator Verification Command

To test the backup pipeline on demand:

```bash
# 1. Trigger manual Job from CronJob
kubectl create job --from=cronjob/postgres-backup-daily manual-s3-backup-verify -n boutique

# 2. Monitor execution logs
kubectl logs -n boutique job/manual-s3-backup-verify -c postgres-dump -f
kubectl logs -n boutique job/manual-s3-backup-verify -c s3-upload -f

# 3. Verify backup object in S3
aws s3 ls s3://boutique-aiops-backups-592668326948-us-east-2/backups/

# 4. Verify KMS encryption header on the uploaded object
aws s3api head-object \
  --bucket boutique-aiops-backups-592668326948-us-east-2 \
  --key backups/<latest-object-name>

# 5. Clean up test job
kubectl delete job manual-s3-backup-verify -n boutique
```

---

## 4. Execution Verification & S3 Inventory

- **CronJob Schedule**: Configured for `0 2 * * *` (02:00 AM IST daily) with `timeZone: Asia/Kolkata`.
- **Encrypted S3 Archives**: Encrypted database backups were verified present in `s3://boutique-aiops-backups-592668326948-us-east-2/backups/`:
  - `ServerSideEncryption: aws:kms`
  - `SSEKMSKeyId: arn:aws:kms:us-east-2:592668326948:key/1e4e2ce3-e642-47a9-a20d-3a47b052918b`
  - `BucketKeyEnabled: true`

---

## 5. Visual Storage Evidence & Restore Distinction

1. [`27-aws-s3-buckets-inventory.png`](27-aws-s3-buckets-inventory.png): AWS S3 Console showing project buckets including `boutique-aiops-backups-592668326948-us-east-2` alongside diagnostic and tfstate buckets.
2. **Restore Evidence**: Actual completed point-in-time SQL restore verification is documented with full terminal logs in [`proof/terminal-outputs/35-isolated-backup-restore-verification.txt`](../terminal-outputs/35-isolated-backup-restore-verification.txt).
