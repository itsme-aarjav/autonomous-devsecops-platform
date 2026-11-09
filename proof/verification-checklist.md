# Verified Project Checklist

These checks summarize **historical evidence** from the live AWS demo. They are not claims that the services are still running.

| Check | Evidence |
| --- | --- |
| EKS cluster and workloads running | [EKS screenshot](kubernetes/20-aws-eks-cluster-info.png), [workload screenshot](kubernetes/21-aws-eks-workloads-status.png) |
| Public storefront and product API responding | [Storefront screenshot](architecture/01-storefront-ui-demo.png), [API log](terminal-outputs/05-storefront-api.txt) |
| Argo CD healthy and synchronized | [Argo CD screenshot](ci-cd/02-argocd-application-overview.png) |
| Prometheus, Alertmanager and Grafana configured | [Monitoring baseline](terminal-outputs/06-observability-baseline.txt), [dashboard index](screenshots/README.md) |
| Real OOMKilled, exit 137 | [OOMKilled log](terminal-outputs/09-aiops-oomkilled.txt) |
| Alert routing and AI-assisted RCA | [Alertmanager](terminal-outputs/12-alertmanager-incident.txt), [AIOps processing](terminal-outputs/13-aiops-processing.txt) |
| Human rejection path | [Rejection](terminal-outputs/17-aiops-human-rejection.txt) |
| Human-approved GitOps remediation | [Approval](terminal-outputs/30-aiops-human-approval-pr.txt), [PR #2](https://github.com/itsme-aarjav/autonomous-devsecops-platform/pull/2) |
| Final canary memory configuration | [Production manifest](../devops/gitops/overlays/production/canary.yml) and subsequent live verification |
| 27 AIOps regression tests | [Test log](terminal-outputs/21-aiops-regression-tests.txt) |
| S3 SQL backup restored and checked | [Restore verification](terminal-outputs/35-isolated-backup-restore-verification.txt) |
| Project AWS resources decommissioned | [Teardown report](terminal-outputs/36-aws-teardown-and-cost-elimination.txt) |

## Evidence counts

- **28** saved screenshots, grouped by topic.
- **36** numbered proof stages across **38** text files.
- Live AWS deployment and recovery were tested before teardown.
- Current GitHub Actions keeps validation jobs but skips ECR publishing and AWS deployment.

## Limits

The residual project cost is **estimated** below `$0.01/month`; this is not a billing invoice. The frontend rollout configuration, the OOMKilled canary test and the database recovery tests are separate demonstrations. No commercial-production uptime or reliability guarantee is claimed.

See the [screenshot index](screenshots/README.md) and [terminal proof index](terminal-outputs/README.md).
