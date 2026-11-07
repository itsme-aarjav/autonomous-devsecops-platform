# Manual AIOps Demonstration Guide

This guide allows human evaluators, operators, and recruiters to personally trigger and observe the complete AIOps autonomous remediation pipeline on live AWS infrastructure.

---

## Architecture Overview

```
Alertmanager Alert
       │
       ▼ (Webhook / SQS FIFO: `boutique-aiops-alert-queue.fifo`)
AIOps Reasoning Agent (Amazon Bedrock Nova Lite `amazon.nova-lite-v1:0`)
       │
       ▼ (Deterministic Policy Evaluation)
DynamoDB RCA & Remediation Proposal (`boutique-aiops-remediations`)
       │
       ▼
Human Operator CLI (`aiops/operator_cli.py`)
       │
       ▼ (Interactive Human Approval)
GitHub Pull Request Opened (`fix/aiops-proposal-...`)
       │
       ▼ (Reviewed Merge into `main`)
Argo CD GitOps Rollout to EKS
```

---

## 1. Safety Invariants

- **Safe Two-Stage Human-in-the-Loop Architecture**:
  - **Stage A**: Fully autonomous incident detection, log correlation, Bedrock root cause analysis (RCA), and deterministic policy gating.
  - **Stage B**: Mandatory human review. Autonomous direct mutations to `main` are strictly forbidden. Approved proposals generate a reviewed GitHub Pull Request.
- **Fail-Closed Policy Gating**:
  - Only allowlisted operations (e.g., replica scaling between 1–5, bounded memory increases up to 1Gi) pass policy.
  - Destructive actions (e.g., node termination, secret modification) are automatically rejected by policy.

---

## 2. Interactive Operator CLI Commands

The operator CLI supports both live AWS-backed mode and offline simulation mode.

### A. List Active Proposals
```bash
# Live mode (queries DynamoDB boutique-aiops-rca-reports)
python3 aiops/operator_cli.py list

# Simulation mode (hermetic test fixtures)
python3 aiops/operator_cli.py list --simulate
```

### B. Inspect Proposal Details & Manifest Diff
```bash
# View full RCA, confidence score, policy decision, and unified git diff
python3 aiops/operator_cli.py show <PROPOSAL_ID>

# Simulation mode
python3 aiops/operator_cli.py show sim-prop-001 --simulate
```

### C. Approve Proposal (Creates GitHub Pull Request)
```bash
# In production/live mode, interactive typing of 'APPROVE' is strictly enforced
python3 aiops/operator_cli.py approve <PROPOSAL_ID>

# Simulation mode
python3 aiops/operator_cli.py approve sim-prop-001 --simulate --yes
```

Upon approval:
1. The engine creates a Git feature branch `fix/aiops-proposal-<id[:8]>`.
2. The engine commits the validated manifest patch.
3. The engine opens a GitHub Pull Request with RCA justification and audit trail.
4. The proposal status updates to `PR_CREATED` in DynamoDB.

### D. Reject Proposal
```bash
# Rejects the proposal with a permanent audit reason
python3 aiops/operator_cli.py reject <PROPOSAL_ID> --reason "Workload scaling denied by SRE"

# Simulation mode
python3 aiops/operator_cli.py reject sim-prop-002 --simulate --yes --reason "Scale rejected by SRE"
```

---

## 3. How to Trigger a Safe Isolated Incident (User Verification)

> [!IMPORTANT]
> **Production Safety Invariant**: Never disrupt core services (`boutique-auth`, `boutique-gateway`, `boutique-frontend`, `boutique-postgres`) to demonstrate AIOps capabilities. The procedure below uses an isolated canary test pod in namespace `boutique` that safely breaches a 32Mi memory boundary without impacting live storefront customer traffic.

### Step 1: Launch the Isolated Canary Memory Pressure Test
Deploy the isolated canary workload under memory pressure into the `boutique` namespace:
```bash
kubectl apply -f devops/gitops/k8s/aiops/isolated-incident-test.yaml
```

Check the canary pod status:
```bash
kubectl get pods -n boutique -l app=canary -w
```
Within a few seconds, the canary container will terminate with `OOMKilled` / `Error` (Exit Code 137). Verify with:
```bash
kubectl describe pod -l app=canary -n boutique | grep -E "Reason:|Exit Code:"
```
Expected output:
```text
    Reason:       OOMKilled
    Exit Code:    137
```

### Step 2: Observe Prometheus & Alertmanager Detection
The Prometheus rule `aiops-pod-oomkilled` evaluates `kube_pod_container_status_last_terminated_reason{reason="OOMKilled", namespace="boutique"} == 1` immediately (`for: 0m`).

To inspect firing alerts in Alertmanager:
```bash
kubectl port-forward svc/kube-prometheus-stack-alertmanager -n monitoring 9093:9093
```
Visit [`http://localhost:9093`](http://localhost:9093) to confirm the `PodOOMKilled` alert is firing.

### Step 3: Observe Autonomous SQS Queueing & Bedrock RCA
1. Alertmanager forwards the webhook payload to the SQS FIFO queue `boutique-aiops-alert-queue.fifo`.
2. The `aiops-assistant` worker daemon ingests the incident payload and queries Amazon Bedrock Nova Lite (`amazon.nova-lite-v1:0`) for root cause analysis and deterministic policy gating.
3. Tail the live assistant logs to watch the autonomous analysis unfold:
   ```bash
   kubectl logs -n boutique deployment/aiops-assistant -f
   ```

### Step 4: Verify Proposal in DynamoDB
The agent persists the structured RCA report and proposed GitOps manifest patch into DynamoDB with status `PENDING_HUMAN_APPROVAL`:
```bash
aws dynamodb scan --region us-east-2 --table-name boutique-aiops-remediations \
  --query 'Items[*].{ProposalID:proposal_id.S, Category:category.S, Status:status.S, Confidence:confidence_score.N}' \
  --output table
```

### Step 5: Review and Approve via Operator CLI
Review the generated proposal using the operator CLI:
```bash
# List pending proposals
python3 aiops/operator_cli.py list

# View detailed RCA and unified diff
python3 aiops/operator_cli.py show <PROPOSAL_ID>

# Review and approve (creates a GitHub Pull Request; strictly forbids direct commits to main)
python3 aiops/operator_cli.py approve <PROPOSAL_ID>
```
Upon typing `APPROVE`:
- A new git branch `fix/aiops-proposal-<id[:8]>` is created.
- The validated remediation manifest patch is committed.
- A GitHub Pull Request is opened with full RCA rationale.
- The PR URL is printed to the operator console.

### Step 6: Restore Canary Baseline State
Once human approval and Pull Request review is complete, restore the healthy baseline configuration:
```bash
kubectl apply -f devops/gitops/overlays/dev/canary.yml
```
Alternatively, merge the generated PR into `main` and let Argo CD automatically synchronize the updated memory limits to the `boutique-canary` deployment on EKS.
Verify the boutique namespace has returned to clean running state:
```bash
kubectl get pods -n boutique -l app=canary
```
