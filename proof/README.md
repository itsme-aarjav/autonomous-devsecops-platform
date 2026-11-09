# Project Evidence

This folder contains screenshots, logs and technical explanations from a **real AWS deployment** of the Autonomous DevSecOps Platform. The cloud infrastructure was deleted after testing to control costs. These are historical proofs, not links to a currently running demo.

## Start here

- [Screenshot index](screenshots/README.md) — **28** screenshots stored in the relevant folders.
- [Terminal evidence index](terminal-outputs/README.md) — **36** numbered stages represented by **38** text files.
- [Historical verification walkthrough](demo-guide.md) — a short guide to the most useful proofs.
- [AIOps approval evidence](terminal-outputs/30-aiops-human-approval-pr.txt) and [GitHub PR #2](https://github.com/itsme-aarjav/autonomous-devsecops-platform/pull/2).
- [PostgreSQL SQL backup restore](terminal-outputs/35-isolated-backup-restore-verification.txt).
- [AWS teardown record](terminal-outputs/36-aws-teardown-and-cost-elimination.txt).

## By topic

| Folder | Evidence |
| --- | --- |
| [`architecture/`](architecture/) | Application, VPC, ALBs, SQS, DynamoDB, AIOps flow |
| [`ci-cd/`](ci-cd/) | Argo CD, deployment topology, ECR |
| [`kubernetes/`](kubernetes/) | EKS cluster and workload status |
| [`monitoring/`](monitoring/) | Grafana and monitoring screenshots |
| [`backup-recovery/`](backup-recovery/) | S3 backup, SQL restore and EBS snapshot documentation |
| [`security/`](security/) | KMS and security design |
| [`cost/`](cost/) | Cost estimates and decommissioning context |

The original screenshot and terminal files were preserved. Explanatory documents describe only what those files support.
