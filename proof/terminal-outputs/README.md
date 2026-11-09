# Terminal Outputs & Live Verification Logs Catalog

This directory contains **38 genuine, sanitized command-line execution transcripts and terminal outputs** organized across **36 numbered proof stages**, captured during live AWS operations on Amazon EKS (`boutique-dev-eks`, `us-east-2`, AWS account `592668326948`).

Together with the 28 visual proofs cataloged in [`proof/screenshots/README.md`](../screenshots/README.md) (and located in their respective proof directories across `proof/`), these logs verify the complete 16-step platform lifecycle: from baseline deployment and e-commerce operation, through Prometheus alert triggering and Amazon Bedrock Nova Lite root cause analysis, to human operator review, reviewed GitHub PR creation, GitOps reconciliation, KMS-encrypted S3 database restore, and cost-eliminating cloud decommissioning.

---

## 16-Step Verification & AIOps Incident Lifecycle

| Step | Phase | Log File(s) | Description & Verification Outcome |
| :---: | :--- | :--- | :--- |
| **01** | Baseline CI/CD | `01-github-ci-baseline.txt` | Clean 10/10 GitHub Actions checks (lint, Trivy scan, multi-stage container builds). |
| **02** | AWS EKS Status | `02-aws-eks-baseline.txt` | Cluster `boutique-dev-eks` active, 3 Bottlerocket nodes, Kubernetes v1.36. |
| **03** | Workloads Health | `03-kubernetes-workloads.txt` | All 26 pods across `boutique`, `monitoring`, `argocd`, and `kube-system` in Running state. |
| **04** | GitOps Image Parity | `04-argo-image-parity.txt` | SHA-256 container digests in Argo CD matching immutable images in private ECR. |
| **05** | Public Storefront API | `05-storefront-api.txt` | HTTPS 200 OK at `https://demo.aarjav.site/api/products` (8 seeded luxury products). |
| **06** | Observability Baseline | `06-observability-baseline.txt` | Prometheus targets 100% UP, Grafana datasources active, Alertmanager ready. |
| **07** | AIOps Safety Preflight | `07-aiops-safety-preflight.txt`<br/>`07-final-readiness.txt` | Validated SQS FIFO, DynamoDB tables, Bedrock Nova Lite model access, and HMAC auth gate. *(2 files for stage 07)*. |
| **08** | Incident Injection | `08-aiops-trigger.txt` | Operator triggers simulated Canary memory pressure (`boutique-canary-trigger`). |
| **09** | Pod OOMKilled | `09-aiops-oomkilled.txt` | Canary pod terminates with exit code 137 (`OOMKilled`) due to cgroup memory limit. |
| **10** | Trigger Cleanup | `10-aiops-trigger-cleanup.txt` | Clean teardown of trigger workload to isolate incident telemetry. |
| **11** | Prometheus Detection | `11-prometheus-oom-alert.txt` | Prometheus fires `PodOOMKilled` alert matching rule `container_memory_working_set_bytes`. |
| **12** | Alertmanager Dispatch | `12-alertmanager-incident.txt` | Alertmanager deduplicates and dispatches JSON alert webhook into SQS FIFO queue. |
| **13** | SQS & LangGraph Ingestion| `13-aiops-processing.txt` | AIOps Assistant dequeues message, normalizes incident, and gathers cluster logs. |
| **14** | Bedrock RCA & DynamoDB | `14-aiops-dynamodb-proposal.txt`<br/>`14-aiops-live-proposals.txt` | Amazon Bedrock Nova Lite computes RCA; proposals persisted to `boutique-aiops-remediations`. *(2 files for stage 14)*. |
| **15** | Proposal Inspection | `15-aiops-proposal-details.txt` | Complete proposal payload showing incident ID, root cause diagnosis, and manifest diff. |
| **16** | Operator CLI Review | `16-aiops-human-review.txt` | Cloud Operator inspects pending proposal in CloudShell CLI (`aiops/operator_cli.py list`). |
| **17** | Human Rejection Flow | `17-aiops-human-rejection.txt` | Operator exercises rejection path: `--status rejected` with human audit reasoning. |
| **18** | Rejection Audit | `18-aiops-rejection-audit.txt` | Confirms proposal state marked `REJECTED` in DynamoDB with audit trail. |
| **19** | Renderer Preflight | `19-renderer-preflight.txt` | Diagnostic preflight for declarative manifest patching engine. |
| **20** | Unified Manifest Diff | `20-renderer-minimal-diff-local.txt` | Surgical YAML diff calculated for canary memory limit bump (`128Mi` &rarr; `256Mi`). |
| **21** | Regression Test Suite | `21-aiops-regression-tests.txt` | 27/27 unit & security regression tests passing (22 approval gate tests + 5 patch tests). |
| **22** | Git Branch Promotion | `22-renderer-github-push.txt` | Safe promotion of tested patching engine to repository. |
| **23** | CI Pipeline Run | `23-renderer-production-pipeline.txt` | GitHub Actions pipeline validates updated codebase without deployment errors. |
| **24** | ECR Image Parity Check | `24-aiops-updated-image-parity.txt` | Verifies container image digest consistency across deployment environments. |
| **25** | Fresh Incident Preflight | `25-aiops-fresh-incident-preflight.txt` | Readiness check prior to end-to-end human approval live run. |
| **26** | Canary State Reset | `26-aiops-canary-reset.txt` | Resetting canary deployment to initial baseline state. |
| **27** | Alert Queue Drain | `27-aiops-alert-reset.txt` | Draining processed messages from SQS FIFO queue. |
| **28** | Fresh OOM Incident | `28-aiops-fresh-oom-incident.txt` | Real OOMKilled incident triggered on canary pod for approval verification. |
| **29** | Operator Review Session | `29-aiops-approval-review.txt` | Operator inspects new proposal in CLI, reviews Bedrock RCA and memory diff. |
| **30** | HMAC Token Approval & PR | `30-aiops-human-approval-pr.txt` | Operator authenticates with HMAC bearer token; CLI opens reviewed GitHub Pull Request. |
| **31** | Approval Audit Trail | `31-aiops-approval-audit.txt` | Confirms proposal state marked `APPROVED` with operator identity, timestamp, and PR URL. |
| **32** | GitOps PR Merge | `32-aiops-gitops-pr-merge.txt` | Reviewed Pull Request merged into `main` branch. |
| **33** | Argo CD Auto-Sync | `33-aiops-gitops-deployment.txt` | Argo CD detects Git change and reconciles canary manifests. *(Note: Log 33 captures the intermediate PR merge verification showing the old canary 64Mi/128Mi configuration; subsequent production overlay records in `devops/gitops/overlays/production/canary.yml` confirm the final remediated 256Mi/512Mi state).* |
| **34** | Post-Fix CI Verification| `34-aiops-ci-regression-fix.txt` | Clean GitHub Actions CI pipeline execution post-merge. |
| **35** | KMS S3 DB Restore | `35-isolated-backup-restore-verification.txt` | Isolated restore of KMS-encrypted S3 PostgreSQL SQL dump (`auth_db_backup_20261108_203012Z.sql.gz`) into ephemeral pod (schema, 8 products, customer records verified). *(Distinct from EBS snapshot recovery).* |
| **36** | Cloud Decommissioning | `36-aws-teardown-and-cost-elimination.txt` | Safe teardown of all project-owned AWS infrastructure (EKS, VPC, ALBs, NAT GW, ECR, DynamoDB, SQS, S3). Estimated project residual cost reduced to < $0.01/month. |
