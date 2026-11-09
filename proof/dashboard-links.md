# Historical Dashboards & Network Isolation Guide

This document explains the dashboard topology and network isolation decisions used during live AWS operations.

---

## 1. Cloud Decommissioning Notice

The live AWS infrastructure has been decommissioned to maintain zero idle costs.

Public dashboard URLs are no longer accessible. Evaluators should review the verified visual proofs in [`proof/monitoring/`](monitoring/04-grafana-cluster-compute-resources.png) and [`proof/ci-cd/`](ci-cd/02-argocd-application-overview.png).

---

## 2. Tested Dashboard Endpoints

During live testing on AWS EKS (`boutique-dev-eks`, `us-east-2`), the platform exposed three distinct web interfaces:

| Dashboard | Historical URL | Purpose & Capabilities | Visual Proof |
| :--- | :--- | :--- | :--- |
| **Boutique Storefront** | `https://demo.aarjav.site` | Customer shopping UI, 8 seeded luxury products, real-time cart, and demo order checkout. | [Storefront Screenshot](architecture/01-storefront-ui-demo.png) |
| **Argo CD UI** | `https://argocd.demo.aarjav.site` | GitOps continuous delivery dashboard showing application sync status and workload topologies. | [Argo CD Screenshot](ci-cd/02-argocd-application-overview.png) |
| **Grafana Visualizations** | `https://grafana.demo.aarjav.site` | Cluster compute metrics, pod memory quotas, storage IOPS, and node hardware telemetry. | [Grafana Screenshot](monitoring/04-grafana-cluster-compute-resources.png) |

---

## 3. Network Isolation Architecture: Why Prometheus Was Kept Private

A key platform engineering decision was keeping **Prometheus** and **Alertmanager** on internal Kubernetes `ClusterIP` networks rather than exposing them through public Load Balancers:

1. **Absence of Native Auth**: Core Prometheus and Alertmanager engines lack built-in user login and multi-tenancy. Exposing them publicly would allow unauthorized users to scrape metrics or silence alerts.
2. **Cost Avoidance**: Securing them at the edge typically requires deploying an AWS Cognito User Pool with ALB OIDC authentication, or a dedicated Bastion host with multi-AZ NAT Gateways. This would add ~$65–$100/month in idle cloud charges.
3. **Tunneling Strategy**: During live operations, operators accessed internal telemetry securely using encrypted Kubernetes API channels:
   ```bash
   # Secure local tunnel to Prometheus
   kubectl port-forward svc/kube-prometheus-stack-prometheus -n monitoring 9090:9090

   # Secure local tunnel to Alertmanager
   kubectl port-forward svc/kube-prometheus-stack-alertmanager -n monitoring 9093:9093
   ```

---

## 4. Related Evidence

- [Grafana Cluster Metrics Screenshot](monitoring/04-grafana-cluster-compute-resources.png): Live dashboard showing 2.74% CPU and 20.5% RAM.
- [Argo CD Topology Screenshot](ci-cd/03-argocd-network-topology.png): Visual graph of Ingress routing to backend services and pods.
- [Observability Baseline Log](terminal-outputs/06-observability-baseline.txt): Terminal verification of scrape targets and healthy pods.
