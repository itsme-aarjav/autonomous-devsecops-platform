# Platform System Architecture

## 1. High-Level Architecture Overview

The **Autonomous DevSecOps & Cloud Operations Platform** is an enterprise-grade cloud architecture combining automated Kubernetes infrastructure, microservices workloads, full GitOps delivery, end-to-end observability, and an event-driven generative AI site reliability engineering (AIOps) assistant.

```mermaid
flowchart TD
    subgraph Client["Public Internet Clients"]
        User["End Users / Recruiters"]
    end

    subgraph AWS["AWS Cloud (us-east-2)"]
        subgraph DNS["Route 53 & ACM"]
            R53["Route 53 Alias Record<br/>demo.aarjav.site"]
            ACM["ACM TLS Certificate<br/>(RSA 2048)"]
        end

        subgraph Ingress["EKS Auto Mode Ingress"]
            ALB["AWS Application Load Balancer<br/>(Internet-Facing, Multi-AZ)"]
        end

        subgraph VPC["Custom VPC (10.1.0.0/16)"]
            subgraph EKS["Amazon EKS Auto Mode (v1.36)"]
                subgraph Nodes["Bottlerocket Worker Nodes"]
                    subgraph Boutique["Namespace: boutique"]
                        FE["Frontend Pods<br/>(React/Vite, Non-Root UID 10001)"]
                        GW["Gateway Pods<br/>(Express API Gateway)"]
                        AUTH["Auth Pod<br/>(TypeScript, JWT Auth)"]
                        DB[("PostgreSQL 16 StatefulSet<br/>(Encrypted EBS gp3 20Gi)")]
                        AIOPS["AIOps Assistant Pod<br/>(FastAPI / Python 3.11)"]
                    end

                    subgraph Monitoring["Namespace: monitoring"]
                        PROM["Prometheus Server"]
                        AM["Alertmanager"]
                        GRAF["Grafana Dashboards"]
                        NODE_EXP["Node Exporter"]
                    end

                    subgraph GitOps["Namespaces: argocd & argo-rollouts"]
                        ARGO["Argo CD Controller"]
                        ROLLOUT["Argo Rollouts Controller"]
                    end
                end
            end

            subgraph AWS_Services["Managed AWS Services"]
                SQS["Amazon SQS FIFO<br/>(Incident Queue + DLQ, KMS Encrypted)"]
                BEDROCK["Amazon Bedrock<br/>(Amazon Nova Lite v1:0)"]
                DDB[("Amazon DynamoDB<br/>(Episodes & RCA Reports)")]
                ECR["Amazon ECR Registries<br/>(auth, gateway, frontend, aiops)"]
            end
        end
    end

    User -->|HTTPS 443| R53
    R53 --> ALB
    ACM -.->|TLS Termination| ALB
    ALB -->|Target IP:3000| FE
    ALB -->|Target IP:3001| GW
    GW --> AUTH
    AUTH --> DB

    PROM -->|Evaluates SLO Rules| AM
    AM -->|Authenticated Webhook| AIOPS
    AIOPS -->|FIFO Enqueue & Deduplication| SQS
    SQS -->|Consume Message| AIOPS
    AIOPS -->|Diagnostic Queries| PROM
    AIOPS -->|K8s Log/Event Gathering| Nodes
    AIOPS -->|Converse API Inference| BEDROCK
    AIOPS -->|Store Episode & RCA| DDB
```

---

## 2. Infrastructure Layer Breakdown

### A. AWS Network Foundation (Terraform Module: `vpc`)
- **VPC CIDR**: `10.1.0.0/16`
- **Subnet Layout**:
  - 3 Public Subnets (`10.1.0.0/24`, `10.1.1.0/24`, `10.1.2.0/24`) for Load Balancers and NAT Gateway egress.
  - 3 Private Subnets (`10.1.10.0/24`, `10.1.11.0/24`, `10.1.12.0/24`) for Kubernetes worker nodes, pods, and private endpoints.
- **Egress Architecture**: Highly resilient single-NAT Gateway topology for dev cost optimization with internet gateway routing.

### B. Amazon EKS Auto Mode Compute Foundation (Terraform Module: `eks`)
- **Kubernetes Version**: `v1.36.4-eks-cfb47f5`
- **Worker Node Hardware**: 3x `m7i-flex.large` (2 vCPU, 8 GiB Memory, Intel Xeon 4th Gen)
- **OS Image**: Bottlerocket OS (EKS Auto, Standard) 2026.10.31 with Linux kernel 6.18
- **Node Automation**: EKS Auto Mode dynamically provisions, scales, and patches EC2 compute capacity without manual node group management.
- **Storage**: AWS EBS CSI Driver natively integrated via EKS Auto Mode with StorageClass `auto-ebs-sc` providing encrypted `gp3` storage with dynamic volume binding.

### C. Continuous Delivery & GitOps
- **Argo CD (`10.11.6` / app `v3.5.6`)**: Tracks git repositories and synchronizes Kubernetes manifests in real-time.
- **Argo Rollouts (`2.43.9` / app `v1.10.2`)**: Enables progressive delivery, blue-green deployments, and canary analysis with automated metric analysis and instant rollback capability.

---

## 3. Microservices Topology

| Service | Language / Stack | Port | Base Image | Security Context |
| :--- | :--- | :--- | :--- | :--- |
| **boutique-frontend** | React / Vite / Nginx | 3000 | Alpine Unprivileged | `runAsUser: 10001`, `runAsNonRoot: true`, `readOnlyRootFilesystem: true` |
| **boutique-gateway** | Node.js / Express | 3001 | Node 20 Slim | `runAsNonRoot: true`, drop capabilities |
| **boutique-auth** | Node.js / TypeScript | 3002 | Node 20 Slim | `runAsNonRoot: true`, drop capabilities |
| **boutique-postgres** | PostgreSQL 15 | 5432 | Postgres 15 Alpine (v15.19) | StatefulSet with 20Gi encrypted persistent storage |
| **aiops-assistant** | Python 3.11 / FastAPI | 8080 | Python 3.11 Slim | `runAsUser: 10001`, `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `dropCaps: ["ALL"]` |
