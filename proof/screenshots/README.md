# Screenshot Index

All **28 screenshots** were captured **before the AWS project was decommissioned**. Each image is stored with its related technical documentation. A screenshot records what the console or dashboard showed at that time; it does not prove that a deleted service is still running.

## CI/CD and Argo CD

| Screenshot | What it shows |
| --- | --- |
| [02-argocd-application-overview.png](../ci-cd/02-argocd-application-overview.png) | Argo CD app status |
| [03-argocd-network-topology.png](../ci-cd/03-argocd-network-topology.png) | Ingress and workload topology |
| [15-argocd-workloads-tree.png](../ci-cd/15-argocd-workloads-tree.png) | Application resource tree |
| [16-argocd-auth-canary-gateway.png](../ci-cd/16-argocd-auth-canary-gateway.png) | Auth, gateway and canary resources |
| [17-argocd-postgres-statefulset-pvc.png](../ci-cd/17-argocd-postgres-statefulset-pvc.png) | PostgreSQL StatefulSet and storage |
| [18-argocd-cronjob-monitoring-ingress.png](../ci-cd/18-argocd-cronjob-monitoring-ingress.png) | CronJob, alerts and Ingress resources |
| [24-aws-ecr-repositories.png](../ci-cd/24-aws-ecr-repositories.png) | Four ECR image repositories |

## Monitoring

| Screenshot | What it shows |
| --- | --- |
| [04-grafana-cluster-compute-resources.png](../monitoring/04-grafana-cluster-compute-resources.png) | Cluster CPU and memory |
| [05-grafana-cluster-memory-network.png](../monitoring/05-grafana-cluster-memory-network.png) | Cluster memory and network |
| [06-grafana-cluster-container-bandwidth.png](../monitoring/06-grafana-cluster-container-bandwidth.png) | Container network bandwidth |
| [07-grafana-cluster-packet-metrics.png](../monitoring/07-grafana-cluster-packet-metrics.png) | Packet-rate metrics |
| [08-grafana-cluster-storage-iops.png](../monitoring/08-grafana-cluster-storage-iops.png) | Storage I/O metrics |
| [09-grafana-boutique-pods-cpu-memory.png](../monitoring/09-grafana-boutique-pods-cpu-memory.png) | Application pod CPU and memory |
| [10-grafana-boutique-pods-memory-network.png](../monitoring/10-grafana-boutique-pods-memory-network.png) | Pod memory and network |
| [11-grafana-boutique-pods-packet-health.png](../monitoring/11-grafana-boutique-pods-packet-health.png) | Pod packet metrics |
| [12-grafana-boutique-pods-storage-io.png](../monitoring/12-grafana-boutique-pods-storage-io.png) | Pod disk I/O |
| [13-grafana-node-exporter-system-load.png](../monitoring/13-grafana-node-exporter-system-load.png) | Node CPU, memory and load |
| [14-grafana-node-exporter-network-disk.png](../monitoring/14-grafana-node-exporter-network-disk.png) | Node network and disk |

## Kubernetes

| Screenshot | What it shows |
| --- | --- |
| [20-aws-eks-cluster-info.png](../kubernetes/20-aws-eks-cluster-info.png) | EKS cluster configuration |
| [21-aws-eks-workloads-status.png](../kubernetes/21-aws-eks-workloads-status.png) | Kubernetes workloads |

## Application and AWS architecture

| Screenshot | What it shows |
| --- | --- |
| [01-storefront-ui-demo.png](../architecture/01-storefront-ui-demo.png) | Demo application storefront |
| [19-aws-vpc-resource-map.png](../architecture/19-aws-vpc-resource-map.png) | VPC and subnets |
| [22-aws-alb-load-balancers.png](../architecture/22-aws-alb-load-balancers.png) | Three load balancers |
| [23-aws-vpc-nat-gateway.png](../architecture/23-aws-vpc-nat-gateway.png) | NAT Gateway |
| [25-aws-dynamodb-tables.png](../architecture/25-aws-dynamodb-tables.png) | AIOps DynamoDB tables |
| [26-aws-sqs-fifo-queues.png](../architecture/26-aws-sqs-fifo-queues.png) | Incident FIFO queues |

## Backup and storage

| Screenshot | What it shows |
| --- | --- |
| [27-aws-s3-buckets-inventory.png](../backup-recovery/27-aws-s3-buckets-inventory.png) | Project S3 buckets |

## Security

| Screenshot | What it shows |
| --- | --- |
| [28-aws-kms-customer-managed-keys.png](../security/28-aws-kms-customer-managed-keys.png) | KMS encryption key |

**For complete verification:** [terminal log index](../terminal-outputs/README.md). The S3 bucket inventory is not proof of restore success; that evidence is in [restore log 35](../terminal-outputs/35-isolated-backup-restore-verification.txt).
