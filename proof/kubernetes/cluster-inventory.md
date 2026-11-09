# Historical EKS Cluster Inventory

The following was observed while the project was running on AWS. **The cluster has since been deleted.**

| Item | Recorded configuration |
| --- | --- |
| Cluster | `boutique-dev-eks` |
| AWS region | `us-east-2` |
| Kubernetes | v1.36 |
| Compute | EKS Auto Mode with Bottlerocket worker nodes |
| Recorded workload snapshot | 26 pods across application and platform namespaces |
| Network | Custom VPC, four subnets across two Availability Zones |
| Persistent storage | PostgreSQL StatefulSet on a 20 GiB EBS gp3 volume |
| Public interfaces | Storefront, Grafana and Argo CD through three AWS ALBs |

## Main namespaces and workloads

- **`boutique`:** Frontend, gateway, authentication service, PostgreSQL, canary test workload, AIOps assistant and backup CronJob.
- **`monitoring`:** Prometheus, Alertmanager, Grafana and monitoring exporters.
- **`argocd`:** GitOps application controller and related components.
- **`argo-rollouts`:** Progressive delivery controller.
- **`kube-system`:** Kubernetes and EKS system components.

The screenshot captures a moment in time. Pod counts changed during testing and should not be interpreted as a permanent service-level guarantee.

## Evidence

- [EKS cluster screenshot](20-aws-eks-cluster-info.png)
- [EKS workloads screenshot](21-aws-eks-workloads-status.png)
- [Raw Kubernetes baseline](../terminal-outputs/03-kubernetes-workloads.txt)
- [Argo CD workload tree](../ci-cd/15-argocd-workloads-tree.png)
- [Teardown confirmation report](../terminal-outputs/36-aws-teardown-and-cost-elimination.txt)
