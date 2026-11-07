# Kubernetes Cluster Topology & Workload Inventory

## 1. Cluster Information

- **Cluster Name**: `boutique-dev-eks`
- **Region**: `us-east-2` (Ohio)
- **Kubernetes Version**: `v1.36.4-eks-cfb47f5`
- **Node Operating System**: Bottlerocket OS (EKS Auto, Standard) 2026.10.31
- **Kernel Version**: `6.18.56 (amd64)`
- **Container Runtime**: `containerd://2.2.9+bottlerocket`
- **EC2 Instance Type**: `m7i-flex.large` (2 vCPU, 8 GiB Memory)

---

## 2. Worker Node Inventory (EKS Auto Mode)

```
NAME                  STATUS   ROLES    INSTANCE-TYPE    ZONE         INTERNAL-IP   OS-IMAGE
i-0132f13b215aa4b96   Ready    <none>   m7i-flex.large   us-east-2a   10.1.10.163   Bottlerocket (EKS Auto, Standard) 2026.10.31
i-0cb22dbe12516c08e   Ready    <none>   m7i-flex.large   us-east-2a   10.1.10.204   Bottlerocket (EKS Auto, Standard) 2026.10.31
i-0ed85ce505ebc5d28   Ready    <none>   m7i-flex.large   us-east-2a   10.1.10.165   Bottlerocket (EKS Auto, Standard) 2026.10.31
```

---

## 3. Workload Pod Inventory Across Namespaces

Total active pods: **24 pods** across 4 namespaces, 100% Running.

### Namespace: `boutique` (Microservices & SRE Agent)
```
NAME                               READY   STATUS    RESTARTS   WORKLOAD-IMAGE
aiops-assistant-7786d9886c-k7hkr   1/1     Running   0          boutique-aiops-assistant@sha256:a5138d28...
auth-6dc95d9fb5-wfl9q              1/1     Running   0          boutique-auth@sha256:502bb869...
boutique-postgres-0                1/1     Running   0          postgres:15-alpine (PostgreSQL 15.19)
frontend-774dbfff6f-m7fcv          1/1     Running   0          boutique-frontend@sha256:5d0a6b98...
frontend-774dbfff6f-nqcrj          1/1     Running   0          boutique-frontend@sha256:5d0a6b98...
gateway-6d5b6dd4f9-kxn5z           1/1     Running   0          boutique-gateway@sha256:5aa9422e...
gateway-6d5b6dd4f9-p9cf6           1/1     Running   0          boutique-gateway@sha256:5aa9422e...
```

### Namespace: `monitoring` (Observability & Telemetry)
```
NAME                                                       READY   STATUS    RESTARTS
alertmanager-kube-prometheus-stack-alertmanager-0          2/2     Running   0
kube-prometheus-stack-grafana-844b68d89b-dsmv5             3/3     Running   0
kube-prometheus-stack-kube-state-metrics-9ddc489d8-htjf4   1/1     Running   0
kube-prometheus-stack-operator-6b56568775-rfhxn            1/1     Running   0
kube-prometheus-stack-prometheus-node-exporter-9fwrn       1/1     Running   0
kube-prometheus-stack-prometheus-node-exporter-fhwbw       1/1     Running   0
kube-prometheus-stack-prometheus-node-exporter-mzj5c       1/1     Running   0
prometheus-kube-prometheus-stack-prometheus-0              2/2     Running   0
```

### Namespace: `argocd` (GitOps Continuous Delivery)
```
NAME                                               READY   STATUS    RESTARTS
argocd-application-controller-0                    1/1     Running   0
argocd-applicationset-controller-5f8844d48d-lf4df  1/1     Running   0
argocd-dex-server-56bc4fcf66-lcrc5                 1/1     Running   0
argocd-notifications-controller-74c84c69f7-r7xr8   1/1     Running   0
argocd-redis-7d8c878f6f-jqlx2                      1/1     Running   0
argocd-repo-server-69d4598d7c-dss46                1/1     Running   0
argocd-server-57c9f4bff5-gvc8x                     1/1     Running   0
```

### Namespace: `argo-rollouts` (Progressive Delivery Engine)
```
NAME                             READY   STATUS    RESTARTS
argo-rollouts-5847b8c58f-txlj9   1/1     Running   0
argo-rollouts-5847b8c58f-vrkm9   1/1     Running   0
```

---

## 4. Ingress & Remote Service Entry Points

```
NAMESPACE    NAME               CLASS   HOSTS                      ADDRESS                                                                   PORTS
boutique     boutique-ingress   alb     demo.aarjav.site           k8s-boutique-boutique-34baedbce1-932352072.us-east-2.elb.amazonaws.com    80, 443
monitoring   grafana-ingress    alb     grafana.demo.aarjav.site   k8s-monitori-grafanai-28ea07b12d-2146813250.us-east-2.elb.amazonaws.com   80, 443
argocd       argocd-ingress     alb     argocd.demo.aarjav.site    k8s-argocd-argocdin-26faf85580-789615604.us-east-2.elb.amazonaws.com      80, 443
```

All 3 entry points enforce TLS termination via AWS Certificate Manager (ACM `*.demo.aarjav.site` & `demo.aarjav.site`), with HTTP &rarr; HTTPS 301 automatic redirection.

---

## 5. Persistent Storage & EBS CSI

```
PersistentVolume:
NAME                                                        CAPACITY   ACCESS MODES   STATUS   CLAIM                                        STORAGECLASS
persistentvolume/pvc-6fa38b95-1d67-4fa2-acbc-34ac6e482c6e   20Gi       RWO            Bound    boutique/postgres-data-boutique-postgres-0   auto-ebs-sc

PersistentVolumeClaim:
NAMESPACE   NAME                                                      STATUS   VOLUME                                     CAPACITY   STORAGECLASS
boutique    persistentvolumeclaim/postgres-data-boutique-postgres-0   Bound    pvc-6fa38b95-1d67-4fa2-acbc-34ac6e482c6e   20Gi       auto-ebs-sc
```
- **Underlying AWS Volume**: `vol-01f1ce50d718b4e69` (gp3, 20Gi, KMS Encrypted with `arn:aws:kms:us-east-2:592668326948:key/bbeb7c58-6210-4ebe-8181-ce9e30b9ac7c`)
- **Automated Backup Snapshot**: `snap-05a3b0ffe3463e280` (Completed, 100%, KMS Encrypted)
- **Restore Verification Test**: Validated on test volume `vol-09c9dcd255219cd44` with isolated verifier; verified and safely cleaned up.
