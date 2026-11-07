# FinOps Cost Model & Infrastructure Economics

## 1. Executive Summary

A core objective of modern cloud engineering is designing systems that achieve production-grade reliability and security while maintaining strict cost governance. Based on actual running AWS resources in `us-east-2`, the **Autonomous DevSecOps Platform** operates with a realistic monthly run-rate range of **\$335.00 — \$345.00 / month** (~**\$11.20 / day**).

---

## 2. Itemized Monthly Cost Breakdown (Verified Active Resources)

| Component | AWS Resource | Sizing / Configuration | Unit Rate | Est. Monthly Cost |
| :--- | :--- | :--- | :--- | :--- |
| **EKS Control Plane** | Amazon EKS Cluster | Managed EKS Auto Mode Control Plane | \$0.10 / hr | \$73.00 |
| **Worker Compute** | EC2 Instances (EKS Auto) | 3x `m7i-flex.large` (2 vCPU, 8 GiB, Bottlerocket) | \$0.08064 / hr &times; 3 | \$176.60 |
| **Ingress & Load Balancing** | Application Load Balancers | 3x ALB (`demo`, `grafana`, `argocd`) | \$0.0225 / hr + LCU &times; 3 | \$48.60 |
| **Network Egress** | NAT Gateway | 1x Single-AZ NAT Gateway + 10GB Data | \$0.045 / hr + data | \$33.50 |
| **Block Storage (EBS)** | Amazon EBS gp3 | 1x 20Gi volume (`vol-01f1ce50d718b4e69`) | \$0.08 / GB-mo | \$1.60 |
| **Backup Storage** | EBS Snapshots | 1x 20Gi (510MB compressed data: `snap-05a3b0ffe3463e280`) | \$0.05 / GB-mo | \$0.10 |
| **Database & Cache** | Amazon DynamoDB | On-Demand Capacity (Episodes, RCA, Remediations) | Pay-per-request | \$0.50 |
| **Messaging & Queues** | Amazon SQS FIFO | Alert Queue + DLQ (Encrypted) | \$0.50 / M requests | \$0.20 |
| **AI Inference (AIOps)** | Amazon Bedrock (Nova Lite)| Serverless Converse API (`amazon.nova-lite-v1:0`) | \$0.06 / M input tokens | \$0.10 |
| **Container Registry** | Amazon ECR | 4 repositories (~5GB stored) | \$0.10 / GB-mo | \$0.50 |
| **Key Management (KMS)** | AWS KMS | Customer Managed CMKs (`bbeb7c58`, `1e4e2ce3`, `fbae32ef`) | \$1.00 / key-mo | \$3.00 |
| **CloudWatch Observability** | AWS CloudWatch | Metrics, log ingestion (cluster control plane) | Pay-per-GB | \$3.50 |
| **Total Estimated Run-Rate**| — | — | — | **\$341.20 / month** |

---

## 3. FinOps Architectural Innovations

### A. EKS Auto Mode Compute Rightsizing
Worker compute utilizes `m7i-flex.large` instances managed by EKS Auto Mode. Compared to standard `m7i.large` instances, `m7i-flex` instances provide a **19% cost reduction** for burstable workloads while delivering Intel Xeon 4th Generation processing power.

### B. Single-NAT Gateway Strategy for Development
A standard multi-AZ deployment deploys 3 NAT Gateways across 3 Availability Zones, adding **~\$100.00/month** in idle NAT charges. For our DEV environment, we route all private subnets through a single resilient NAT Gateway, immediately saving over **50%** of network infrastructure overhead without sacrificing security isolation.

### C. Serverless Pay-Per-Token AIOps vs Self-Hosted LLMs
Hosting a dedicated open-source 7B or 13B LLM (such as Llama 3 or Mistral) on AWS requires at least an `accelerated computing` instance (e.g. `g5.xlarge` with 1x NVIDIA A10G GPU), costing **\$735.00 / month** in idle GPU compute.

By utilizing **Amazon Bedrock (Amazon Nova Lite)** through the serverless Converse API:
- The system only incurs cost when an alert fires.
- Cost per incident investigation: **< \$0.0005** (less than half of one tenth of a cent).
- Total monthly savings: **over \$730.00 / month** (99.9% cost reduction).
