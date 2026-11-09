# Daily PostgreSQL Backup to S3

During the live AWS deployment, a Kubernetes CronJob backed up the PostgreSQL `auth_db` database every day at **2:00 AM India time**. The cloud environment has since been decommissioned.

## Backup workflow

1. A CronJob ran on schedule `0 2 * * *` with `timeZone: Asia/Kolkata`.
2. A `postgres:15-alpine` init container created a SQL dump using `pg_dump`.
3. The job checked the dump size, compressed it using gzip and checked gzip integrity.
4. An AWS CLI container uploaded the resulting `.sql.gz` file to an S3 bucket.
5. S3 server-side encryption used the project customer-managed AWS KMS key.
6. The job checked the uploaded object metadata to confirm encryption.

Source configuration: [`devops/gitops/overlays/production/backup-cronjob.yml`](../../devops/gitops/overlays/production/backup-cronjob.yml).

## Access and security

The job used a dedicated Kubernetes ServiceAccount (`postgres-backup`) and AWS role for S3/KMS access rather than embedding AWS access keys in the backup script. PostgreSQL credentials came from a Kubernetes Secret.

## Real verification

The saved backup `auth_db_backup_20261108_203012Z.sql.gz` passed a gzip integrity check. It was restored into a temporary PostgreSQL pod, and five tables plus row counts and eight product records were checked. The temporary pod was removed after testing.

- [Actual SQL restore log](../terminal-outputs/35-isolated-backup-restore-verification.txt)
- [S3 bucket screenshot](27-aws-s3-buckets-inventory.png)
- [Separate EBS snapshot recovery](restore-verification.md)

**Current status:** The backup bucket and KMS key were scheduled for removal or deleted as part of teardown. These steps describe the historical configuration, not an active daily backup.
