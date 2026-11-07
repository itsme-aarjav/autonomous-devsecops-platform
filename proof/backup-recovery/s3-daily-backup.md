# Real Daily PostgreSQL S3 Backup Architecture

> **Target Environment**: AWS Account `592668326948` | Region `us-east-2` | Cluster `boutique-dev-eks`  
> **S3 Backup Destination**: `s3://boutique-aiops-backups-592668326948-us-east-2/backups/`  
> **AWS KMS Key ID**: `1e4e2ce3-e642-47a9-a20d-3a47b052918b`  
> **Kubernetes CronJob**: `postgres-backup-daily` in namespace `boutique`  
> **Schedule**: Daily at 02:00 AM IST (`schedule: "0 2 * * *"`, `timeZone: "Asia/Kolkata"`)

---

## 1. Architectural Overview

The database backup pipeline uses a production two-stage decoupled pod architecture:

```
┌────────────────────────────────────────────────────────────────────────┐
│               Kubernetes CronJob: postgres-backup-daily                │
├───────────────────────────────────┬────────────────────────────────────┤
│ Stage 1: initContainer            │ Stage 2: container                 │
│ Image: postgres:15-alpine         │ Image: public.ecr.aws/aws-cli      │
├───────────────────────────────────┼────────────────────────────────────┤
│ 1. Connects to internal DB        │ 1. Inherits shared volume /backup  │
│    (boutique-postgres-0:5432)     │ 2. Reads SQL gzip archive          │
│ 2. Executes pg_dump               │ 3. Executes aws s3 cp with:        │
│ 3. Compresses with gzip -9        │    --sse aws:kms                   │
│ 4. Verifies size (> 500 bytes)    │    --sse-kms-key-id <kms-key-id>   │
│ 5. Validates gzip integrity (-t)  │ 4. Executes aws s3api head-object  │
│ 6. Writes to shared /backup       │    verifying S3 metadata           │
└───────────────────────────────────┴────────────────────────────────────┘
```

---

## 2. Security and IAM Policy

The CronJob uses the `aiops-assistant` ServiceAccount bound to IAM Role `boutique-dev-eks-aiops-agent-role` via IAM Roles for Service Accounts (IRSA).

Attached IAM Policy (`boutique-backup-s3-access`):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::boutique-aiops-backups-592668326948-us-east-2",
        "arn:aws:s3:::boutique-aiops-backups-592668326948-us-east-2/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "kms:Encrypt",
        "kms:Decrypt",
        "kms:ReEncrypt*",
        "kms:GenerateDataKey*",
        "kms:DescribeKey"
      ],
      "Resource": "arn:aws:kms:us-east-2:592668326948:key/1e4e2ce3-e642-47a9-a20d-3a47b052918b"
    }
  ]
}
```

---

## 3. Manual Operator Verification Command

To test the backup immediately on demand:

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
