# Monitoring and Observability

The project used Prometheus, Alertmanager and Grafana to understand Kubernetes health and detect incidents while the AWS cluster was running.

## Roles

| Component | What it did |
| --- | --- |
| Prometheus | Collected metrics from Kubernetes, nodes and application workloads |
| ServiceMonitor / PrometheusRule | Defined monitored targets and alert conditions |
| Alertmanager | Grouped alerts and sent incident notifications |
| Grafana | Displayed CPU, memory, networking and storage dashboards |
| Node Exporter | Collected worker-node system metrics |
| AIOps assistant | Consumed incident messages and investigated the problem |

## Real incident

The separate test canary exceeded its memory limit and was terminated with **OOMKilled (exit code 137)**. Prometheus detected the problem, Alertmanager routed the alert and the AIOps workflow started its investigation.

- [OOMKilled result](../terminal-outputs/09-aiops-oomkilled.txt)
- [Prometheus alert](../terminal-outputs/11-prometheus-oom-alert.txt)
- [Alertmanager event](../terminal-outputs/12-alertmanager-incident.txt)

## Saved dashboards

The **11 Grafana screenshots** are in this folder:

- [Cluster compute](04-grafana-cluster-compute-resources.png)
- [Cluster memory and network](05-grafana-cluster-memory-network.png)
- [Container bandwidth](06-grafana-cluster-container-bandwidth.png)
- [Packet metrics](07-grafana-cluster-packet-metrics.png)
- [Storage IOPS](08-grafana-cluster-storage-iops.png)
- [Pod CPU and memory](09-grafana-boutique-pods-cpu-memory.png)
- [Pod memory and networking](10-grafana-boutique-pods-memory-network.png)
- [Pod packet health](11-grafana-boutique-pods-packet-health.png)
- [Pod storage I/O](12-grafana-boutique-pods-storage-io.png)
- [Node system load](13-grafana-node-exporter-system-load.png)
- [Node network and disk](14-grafana-node-exporter-network-disk.png)

The dashboards are historical screenshots. The live Grafana endpoint was removed during AWS teardown.
