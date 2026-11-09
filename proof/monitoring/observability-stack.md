# Observability & Monitoring Infrastructure

## 1. Monitoring Architecture (kube-prometheus-stack)

The observability subsystem is orchestrated using the CoreOS Prometheus Operator, providing declarative Kubernetes Custom Resource Definitions (CRDs) to manage Prometheus instances, Alertmanager clusters, ServiceMonitors, and PodMonitors.

### Core Components:
1. **Prometheus Server**: Scrapes metrics defined by Kubernetes `ServiceMonitor` CRDs every 30 seconds. Configured with 10-day retention and persistent TSDB storage.
2. **Alertmanager**: Deduplicates, groups, and routes active Prometheus alerts based on severity and namespace labels.
3. **Node Exporter**: DaemonSet running on every Bottlerocket node (`9fwrn`, `fhwbw`, `mzj5c`) exposing hardware and Linux OS metrics.
4. **kube-state-metrics**: Listens to the Kubernetes API server and generates metrics on the health of deployments, replica sets, pods, and persistent volumes.
5. **Grafana**: Visualizes metrics through preconfigured dashboards for cluster health, namespace capacity, container networking, and application latency.

---

## 2. Active ServiceMonitors

| ServiceMonitor Name | Namespace | Target Workload | Endpoints |
| :--- | :--- | :--- | :--- |
| `kube-prometheus-stack-alertmanager` | `monitoring` | Alertmanager Pods | `/metrics` on 9093 |
| `kube-prometheus-stack-apiserver` | `monitoring` | EKS Control Plane API | `/metrics` on 443 |
| `kube-prometheus-stack-coredns` | `monitoring` | CoreDNS Pods | `/metrics` on 9153 |
| `kube-prometheus-stack-grafana` | `monitoring` | Grafana Pods | `/metrics` on 3000 |
| `kube-prometheus-stack-kube-state-metrics`| `monitoring` | kube-state-metrics | `/metrics` on 8080 |
| `kube-prometheus-stack-kubelet` | `monitoring` | Kubelet cAdvisor | `/metrics`, `/metrics/cadvisor` |
| `kube-prometheus-stack-operator` | `monitoring` | Prometheus Operator | `/metrics` on 8080 |
| `kube-prometheus-stack-prometheus` | `monitoring` | Prometheus Engine | `/metrics` on 9090 |
| `kube-prometheus-stack-prometheus-node-exporter` | `monitoring` | Node Exporter DaemonSet | `/metrics` on 9100 |

---

## 3. Alertmanager & AIOps Webhook Integration

Alertmanager is configured to forward firing infrastructure alerts to the internal AIOps Assistant endpoint:

```yaml
receivers:
  - name: aiops-webhook
    webhook_configs:
      - url: 'http://aiops-assistant.boutique.svc.cluster.local:8080/api/v1/alerts'
        send_resolved: true
        http_config:
          bearer_token: '<AIOPS_WEBHOOK_BEARER_TOKEN>'
route:
  receiver: aiops-webhook
  group_by: ['alertname', 'namespace', 'pod']
  group_wait: 10s
  group_interval: 30s
  repeat_interval: 1h
```

When an incident fires (such as `PodOOMKilled` or `KubePodCrashLooping`), Alertmanager bundles the alert labels and sends a webhook to the AIOps agent, initiating automated diagnosis.

---

## 4. Visual Observability Dashboards

The following Grafana visual proofs captured during live operational monitoring are cataloged in this directory:

1. [`04-grafana-cluster-compute-resources.png`](04-grafana-cluster-compute-resources.png): Cluster CPU Utilization (2.74%) & RAM Utilization (20.5%).
2. [`05-grafana-cluster-memory-network.png`](05-grafana-cluster-memory-network.png): Memory requests/limits and live network bandwidth by namespace.
3. [`06-grafana-cluster-container-bandwidth.png`](06-grafana-cluster-container-bandwidth.png): Container bandwidth received and transmitted per second.
4. [`07-grafana-cluster-packet-metrics.png`](07-grafana-cluster-packet-metrics.png): Transmitted packet rates and confirmation of zero packet drops.
5. [`08-grafana-cluster-storage-iops.png`](08-grafana-cluster-storage-iops.png): EBS gp3 storage IOPS and read/write throughput.
6. [`09-grafana-boutique-pods-cpu-memory.png`](09-grafana-boutique-pods-cpu-memory.png): Namespace pod CPU and memory utilization breakdown.
7. [`10-grafana-boutique-pods-memory-network.png`](10-grafana-boutique-pods-memory-network.png): Pod memory quotas vs physical usage.
8. [`11-grafana-boutique-pods-packet-health.png`](11-grafana-boutique-pods-packet-health.png): Pod-level packet transmission rates and zero drops.
9. [`12-grafana-boutique-pods-storage-io.png`](12-grafana-boutique-pods-storage-io.png): Postgres database pod disk I/O and throughput.
10. [`13-grafana-node-exporter-system-load.png`](13-grafana-node-exporter-system-load.png): Bottlerocket node system load, CPU (1.9%), and RAM (14.6%).
11. [`14-grafana-node-exporter-network-disk.png`](14-grafana-node-exporter-network-disk.png): Worker node hardware telemetry (ENIs, disk throughput, latency).
