# Historical Dashboards

The AWS demo is **no longer running**. This page explains which interfaces were available during live testing and what was captured.

| Interface | Purpose | Saved evidence |
| --- | --- | --- |
| Storefront | Product catalog and demo application | [Storefront screenshot](architecture/01-storefront-ui-demo.png) |
| Argo CD | GitOps application health, sync and resource tree | [Argo CD screenshot](ci-cd/02-argocd-application-overview.png) |
| Grafana | CPU, memory, network and disk metrics | [Grafana screenshot](monitoring/04-grafana-cluster-compute-resources.png) |
| Prometheus | Monitoring metrics and alert rules | [Monitoring details](monitoring/observability-stack.md) |
| Alertmanager | Grouping and routing alerts | [Alert evidence](terminal-outputs/12-alertmanager-incident.txt) |

The first three interfaces previously had HTTPS addresses under `demo.aarjav.site`. Prometheus and Alertmanager used internal Kubernetes services; operators inspected them through `kubectl port-forward` instead of exposing a public load balancer.

To review the platform now, use the [28-screenshot index](screenshots/README.md). There is no active dashboard login.
