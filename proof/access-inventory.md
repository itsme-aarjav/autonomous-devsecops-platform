# Historical Service Access

This page records how the deployed project was accessed **before AWS teardown**. None of the demo endpoints below should be treated as currently active.

## Web interfaces

| Service | Historical URL | Verification |
| --- | --- | --- |
| Storefront | `https://demo.aarjav.site` | [Application screenshot](architecture/01-storefront-ui-demo.png) and [HTTP response](terminal-outputs/05-storefront-api.txt) |
| Argo CD | `https://argocd.demo.aarjav.site` | [Application overview](ci-cd/02-argocd-application-overview.png) |
| Grafana | `https://grafana.demo.aarjav.site` | [Metrics screenshot](monitoring/04-grafana-cluster-compute-resources.png) |

AWS Application Load Balancers handled HTTPS traffic using Route 53 DNS records and AWS Certificate Manager certificates.

## Authentication

- The storefront used an authentication service with JSON Web Tokens (JWTs).
- Argo CD and Grafana had their own administrative login mechanisms.
- AWS Secrets Manager and Kubernetes Secrets were used for application credentials.
- Prometheus and Alertmanager did not have public Ingress endpoints; operators accessed them through Kubernetes port forwarding during testing.

**Do not try old credentials or restore deleted services.** For interviews, use the [proof index](README.md), saved screenshots, historical [CI runs](https://github.com/itsme-aarjav/autonomous-devsecops-platform/actions), and [remediation PR](https://github.com/itsme-aarjav/autonomous-devsecops-platform/pull/2).
