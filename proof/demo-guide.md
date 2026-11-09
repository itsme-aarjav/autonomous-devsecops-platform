# Interviewer Walkthrough

The AWS cluster was **decommissioned after live testing**. This guide helps an interviewer review the saved evidence without needing a working demo URL.

## Suggested review order

1. **See the application:** [Storefront screenshot](architecture/01-storefront-ui-demo.png) and [HTTP/API result](terminal-outputs/05-storefront-api.txt).
2. **See the infrastructure:** [VPC](architecture/19-aws-vpc-resource-map.png), [EKS](kubernetes/20-aws-eks-cluster-info.png) and [ALBs](architecture/22-aws-alb-load-balancers.png).
3. **See GitOps and monitoring:** [Argo CD health](ci-cd/02-argocd-application-overview.png) and [Grafana](monitoring/04-grafana-cluster-compute-resources.png).
4. **Follow the real incident:** [OOMKilled exit 137](terminal-outputs/09-aiops-oomkilled.txt) → [Alertmanager](terminal-outputs/12-alertmanager-incident.txt) → [AIOps processing](terminal-outputs/13-aiops-processing.txt).
5. **Review human control:** [Rejected proposal](terminal-outputs/17-aiops-human-rejection.txt), [approved proposal](terminal-outputs/30-aiops-human-approval-pr.txt) and [merged PR #2](https://github.com/itsme-aarjav/autonomous-devsecops-platform/pull/2).
6. **Check recovery:** [Successful live GitHub Actions run](https://github.com/itsme-aarjav/autonomous-devsecops-platform/actions/runs/42529170045) and [final canary settings](../devops/gitops/overlays/production/canary.yml).
7. **Check data recovery:** [S3 PostgreSQL backup restore](terminal-outputs/35-isolated-backup-restore-verification.txt).
8. **Check cloud cleanup:** [Teardown evidence](terminal-outputs/36-aws-teardown-and-cost-elimination.txt).

The canary OOMKilled test and the frontend Argo Rollouts release strategy are **separate** parts of the project. Historical proof `33` records an intermediate state, not the final memory settings.

For all available evidence, see the [terminal log index](terminal-outputs/README.md) and [screenshot index](screenshots/README.md).
