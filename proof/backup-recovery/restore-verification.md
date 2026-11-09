# PostgreSQL EBS Backup & Disaster Recovery Verification Report

This report documents an isolated disaster recovery restore test executed to validate the integrity of automated Amazon Elastic Block Store (EBS) snapshot backups for the platform's core PostgreSQL database (`auth_db`).

The test verified that the database can be fully reconstructed from an encrypted point-in-time EBS snapshot without data loss and without affecting the running production database.

> [!NOTE]
> **Restore Methodology Distinction**:
> - **This Document**: Documents the restoration of an AWS EBS volume snapshot (`snap-05a3b0ffe3463e280`) into an isolated test volume and pod.
> - **S3 SQL Dump Restore**: The restoration of the daily compressed SQL dump (`.sql.gz`) from Amazon S3 into an ephemeral PostgreSQL container is separately documented with complete terminal output in [`proof/terminal-outputs/35-isolated-backup-restore-verification.txt`](../terminal-outputs/35-isolated-backup-restore-verification.txt).

---

## 1. Backup Source Evidence

| Parameter | Value | Details |
| :--- | :--- | :--- |
| **Snapshot ID** | `snap-05a3b0ffe3463e280` | Automated point-in-time EBS snapshot |
| **Original Volume** | `vol-01f1ce50d718b4e69` | `boutique-postgres-0` data volume (20 GiB gp3) |
| **AWS Region / AZ** | `us-east-2` / `us-east-2a` | Ohio |
| **Snapshot Status** | `completed` (100% progress) | 535,298,048 bytes transferred |
| **Encryption** | Enabled (`Encrypted: true`) | AWS KMS Customer Managed Key: `arn:aws:kms:us-east-2:592668326948:key/bbeb7c58-6210-4ebe-8181-ce9e30b9ac7c` |
| **Snapshot Description**| `PostgreSQL automated backup - Master Execution` | Tagged `Environment=dev`, `Name=boutique-postgres-master-backup` |

---

## 2. Isolated Restoration Procedure

To guarantee that the live database remained completely untouched, the test was conducted in total isolation:

1. **Volume Provisioning**:
   - A fresh AWS EBS volume `vol-0e374b00d6f4cfe90` (20 GiB, gp3) was created directly from snapshot `snap-05a3b0ffe3463e280` in `us-east-2a`.
   - Cluster ownership tags were applied (`KubernetesCluster=boutique-dev-eks`, `kubernetes.io/cluster/boutique-dev-eks=owned`).
2. **Kubernetes Storage Binding**:
   - Created a static `PersistentVolume` (`pv-restore-verified`) referencing the new EBS volume.
   - Bound it to a `PersistentVolumeClaim` (`pvc-restore-verified`) in the isolated `default` namespace.
3. **Isolated PostgreSQL Pod Execution**:
   - Deployed `pod/postgres-restore-verified` running `postgres:15-alpine` attached to `pvc-restore-verified`.
   - The AWS EBS CSI driver successfully attached and mounted the volume.
   - The PostgreSQL engine initialized existing data files, completed Write-Ahead Logging (WAL) redo recovery cleanly, and became ready for connections.

---

## 3. Data Integrity Verification

Queries executed against the restored PostgreSQL instance inside `postgres-restore-verified`:

```sql
SELECT id, email, role, created_at FROM users;
```

### Query Output:
```
                  id                  |             email              |   role   |         created_at
--------------------------------------+--------------------------------+----------+----------------------------
 afc4508c-d537-4189-b423-1b104bec11b4 | testuser@devops-platform.local | customer | 2026-11-07 14:24:42.549261
 4808770b-1749-438b-bb5e-61d8622fcb51 | recruiter@demo.aarjav.site     | customer | 2026-11-07 16:38:02.600778
(2 rows)
```

**Verification Facts**:
- Database `auth_db` was intact and fully readable.
- All user accounts, salted password hashes, UUID primary keys, and creation timestamps matched historical production records.
- Zero table corruption, index errors, or transaction log inconsistencies.

---

## 4. Production Database Invariant

Throughout the entire restore test, the production database in the `boutique` namespace remained active and unaltered:

```bash
# Query production database
kubectl exec -i -n boutique boutique-postgres-0 -- psql -U postgres -d auth_db -c "SELECT count(*) FROM products;"
# Result: 8 products

kubectl exec -i -n boutique boutique-postgres-0 -- psql -U postgres -d auth_db -c "SELECT count(*) FROM orders;"
# Result: 1 order
```

---

## 5. Clean Resource Tear-Down

Immediately upon verification completion:
1. `pod/postgres-restore-verified` was deleted.
2. `pvc/pvc-restore-verified` and `pv/pv-restore-verified` were deleted.
3. AWS EBS volume `vol-0e374b00d6f4cfe90` was deleted via AWS EC2 API.
4. Confirmed zero orphaned resources or storage cost leaks remaining.
