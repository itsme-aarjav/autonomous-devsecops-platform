# Observability & Monitoring Infrastructure

## 1. Monitoring Architecture (kube-prometheus-stack 92.22.0)

The observability subsystem is orchestrated using the CoreOS Prometheus Operator, providing cloud-native CRDs to manage Prometheus instances, Alertmanager clusters, ServiceMonitors, and PodMonitors declaratively.

### Core Components Deployed:
1. **Prometheus Server**: Statefully scrapes targets defined by Kubernetes `ServiceMonitor` CRDs every 30 seconds. Configured with 10-day retention and persistent TSDB storage.
2. **Alertmanager**: Deduplicates, groups, and routes active Prometheus alerts based on severity and namespace labels.
3. **Node Exporter**: DaemonSet running on every Bottlerocket node (`9fwrn`, `fhwbw`, `mzj5c`) exposing hardware and OS metrics.
4. **kube-state-metrics**: Listens to the Kubernetes API server and generates metrics about the health of deployments, replica sets, pods, and persistent volumes.
5. **Grafana**: Visualizes metrics through pre-provisioned dashboards for cluster health, namespace capacity, and application latency.

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

When an incident fires (such as `PodOOMKilled` or `KubePodCrashLooping`), Alertmanager immediately bundles the telemetry labels and POSTs to the AIOps agent, initiating autonomous diagnosis.
