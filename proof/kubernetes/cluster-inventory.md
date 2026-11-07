# Kubernetes Cluster Topology & Workload Inventory

## 1. Cluster Information

- **Cluster Name**: `boutique-dev-eks`
- **Region**: `us-east-2` (Ohio)
- **Kubernetes Version**: `v1.36.4-eks-cfb47f5`
- **Node Operating System**: Bottlerocket OS (EKS Auto, Standard) 2026.10.31
- **Kernel Version**: `6.18.56 (amd64)`
- **Container Runtime**: `containerd://2.2.9+bottlerocket`

---

## 2. Worker Node Inventory (EKS Auto Mode)

```
NAME                  STATUS   ROLES    AGE     VERSION               INTERNAL-IP   EXTERNAL-IP   OS-IMAGE                                                               KERNEL-VERSION    CONTAINER-RUNTIME
i-0132f13b215aa4b96   Ready    <none>   35m     v1.36.4-eks-cfb47f5   10.1.10.163   <none>        Bottlerocket (EKS Auto, Standard) 2026.10.31 (aws-k8s-1.36-standard)   6.18.56 (amd64)   containerd://2.2.9+bottlerocket
i-0cb22dbe12516c08e   Ready    <none>   4h53m   v1.36.4-eks-cfb47f5   10.1.10.204   <none>        Bottlerocket (EKS Auto, Standard) 2026.10.31 (aws-k8s-1.36-standard)   6.18.56 (amd64)   containerd://2.2.9+bottlerocket
i-0ed85ce505ebc5d28   Ready    <none>   174m    v1.36.4-eks-cfb47f5   10.1.10.165   <none>        Bottlerocket (EKS Auto, Standard) 2026.10.31 (aws-k8s-1.36-standard)   6.18.56 (amd64)   containerd://2.2.9+bottlerocket
```

---

## 3. Workload Pod Inventory Across Namespaces

Total active pods: **24 pods** across 4 namespaces, 100% Running.

### Namespace: `boutique` (Application & AIOps)
```
NAME                               READY   STATUS    RESTARTS   AGE    IP            NODE
aiops-assistant-7786d9886c-k7hkr   1/1     Running   0          25m    10.1.10.49    i-0132f13b215aa4b96
auth-6dc95d9fb5-wfl9q              1/1     Running   0          174m   10.1.10.17    i-0ed85ce505ebc5d28
boutique-postgres-0                1/1     Running   0          179m   10.1.10.73    i-0cb22dbe12516c08e
frontend-774dbfff6f-m7fcv          1/1     Running   0          174m   10.1.10.16    i-0ed85ce505ebc5d28
frontend-774dbfff6f-nqcrj          1/1     Running   0          174m   10.1.10.19    i-0ed85ce505ebc5d28
gateway-6d5b6dd4f9-kxn5z           1/1     Running   0          174m   10.1.10.20    i-0ed85ce505ebc5d28
gateway-6d5b6dd4f9-p9cf6           1/1     Running   0          174m   10.1.10.18    i-0ed85ce505ebc5d28
```

### Namespace: `monitoring` (Observability & Telemetry)
```
NAME                                                       READY   STATUS    RESTARTS   AGE
alertmanager-kube-prometheus-stack-alertmanager-0          2/2     Running   0          4h33m
kube-prometheus-stack-grafana-844b68d89b-dsmv5             3/3     Running   0          4h33m
kube-prometheus-stack-kube-state-metrics-9ddc489d8-htjf4   1/1     Running   0          4h33m
kube-prometheus-stack-operator-6b56568775-rfhxn            1/1     Running   0          4h33m
kube-prometheus-stack-prometheus-node-exporter-9fwrn       1/1     Running   0          174m
kube-prometheus-stack-prometheus-node-exporter-fhwbw       1/1     Running   0          35m
kube-prometheus-stack-prometheus-node-exporter-mzj5c       1/1     Running   0          4h33m
prometheus-kube-prometheus-stack-prometheus-0              2/2     Running   0          4h33m
```

### Namespace: `argocd` (GitOps Continuous Delivery)
```
NAME                                               READY   STATUS    RESTARTS   AGE
argocd-application-controller-0                    1/1     Running   0          4h51m
argocd-applicationset-controller-5f8844d48d-lf4df  1/1     Running   0          4h51m
argocd-dex-server-56bc4fcf66-lcrc5                 1/1     Running   0          4h51m
argocd-notifications-controller-74c84c69f7-r7xr8   1/1     Running   0          4h51m
argocd-redis-7d8c878f6f-jqlx2                      1/1     Running   0          4h51m
argocd-repo-server-69d4598d7c-dss46                1/1     Running   0          4h51m
argocd-server-57c9f4bff5-gvc8x                     1/1     Running   0          4h51m
```

### Namespace: `argo-rollouts` (Progressive Delivery Engine)
```
NAME                             READY   STATUS    RESTARTS   AGE
argo-rollouts-5847b8c58f-txlj9   1/1     Running   0          4h51m
argo-rollouts-5847b8c58f-vrkm9   1/1     Running   0          4h51m
```

---

## 4. Ingress & Load Balancing

```
NAMESPACE   NAME               CLASS   HOSTS              ADDRESS                                                                  PORTS
boutique    boutique-ingress   alb     demo.aarjav.site   k8s-boutique-boutique-34baedbce1-932352072.us-east-2.elb.amazonaws.com   80, 443
```

- **Target Groups**:
  - `k8s-boutique-frontend-8249621266`: 2/2 targets healthy (IP targets on port 3000)
  - `k8s-boutique-gateway-bb03078129`: 2/2 targets healthy (IP targets on port 3001)

---

## 5. Persistent Storage & EBS CSI

```
PersistentVolume:
NAME                                                        CAPACITY   ACCESS MODES   RECLAIM POLICY   STATUS   CLAIM                                        STORAGECLASS
persistentvolume/pvc-6fa38b95-1d67-4fa2-acbc-34ac6e482c6e   20Gi       RWO            Delete           Bound    boutique/postgres-data-boutique-postgres-0   auto-ebs-sc

PersistentVolumeClaim:
NAMESPACE   NAME                                                      STATUS   VOLUME                                     CAPACITY   STORAGECLASS
boutique    persistentvolumeclaim/postgres-data-boutique-postgres-0   Bound    pvc-6fa38b95-1d67-4fa2-acbc-34ac6e482c6e   20Gi       auto-ebs-sc
```
- **Underlying AWS Volume**: `vol-01f1ce50d718b4e69` (gp3, 20Gi, KMS Encrypted)
- **Backup Snapshot**: `snap-05a3b0ffe3463e280` (Completed, 100%, Encrypted)
