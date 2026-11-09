# PostgreSQL EBS Snapshot Recovery Test

This page records a **historical EBS volume snapshot** test. It is different from the daily S3 SQL backup restore documented in [terminal proof 35](../terminal-outputs/35-isolated-backup-restore-verification.txt).

## What was tested

An encrypted EBS snapshot of the PostgreSQL data volume was used to create a **separate 20 GiB gp3 test volume**. A temporary Kubernetes PersistentVolume, PersistentVolumeClaim and PostgreSQL pod used that restored volume. The test checked that PostgreSQL started and data could be queried.

| Item | Historical identifier |
| --- | --- |
| Source snapshot | `snap-05a3b0ffe3463e280` |
| Original PostgreSQL volume | `vol-01f1ce50d718b4e69` |
| Temporary restored volume | `vol-0e374b00d6f4cfe90` |
| Temporary pod | `postgres-restore-verified` |
| Region | `us-east-2` |

The historical report recorded readable user data and an active production database during the test. It did **not** include separate comprehensive index or corruption tests, so this is a successful restore/readability check—not a guarantee that every database invariant was tested.

## Cleanup

The temporary restore pod, volume claim, volume and test storage were removed after verification. The original snapshot and project-owned cloud infrastructure were later deleted during final teardown.

## Separate S3 SQL restore test

The later [S3 SQL restore log](../terminal-outputs/35-isolated-backup-restore-verification.txt) used a compressed `.sql.gz` dump in a temporary pod with `emptyDir` storage. That test verified **five tables** and **eight products**, without creating a persistent test volume. It used normal cluster networking and was **not network-air-gapped**.

See [daily S3 backup design](s3-daily-backup.md) for how the SQL backup was created.
