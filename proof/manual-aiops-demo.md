# Manual AIOps Demonstration Guide

This guide allows human evaluators, operators, and recruiters to personally trigger and observe the complete AIOps autonomous remediation pipeline on live AWS infrastructure.

---

## Architecture Overview

```
Alertmanager Alert
       │
       ▼ (Webhook / SQS FIFO)
AIOps Reasoning Agent (Bedrock Claude 3.5 Sonnet)
       │
       ▼ (Deterministic Policy Evaluation)
DynamoDB RCA & Remediation Proposal (`boutique-aiops-rca-reports`)
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

## 3. How to Trigger a Live Synthetic Incident (Optional)

To trigger a live test alert on the EKS cluster and observe the agent in action:

1. **Inject synthetic high memory pressure or replica degradation**:
   ```bash
   kubectl scale deployment auth -n boutique --replicas=0
   ```
2. **Observe Prometheus & Alertmanager**:
   - Port-forward Alertmanager: `kubectl port-forward svc/kube-prometheus-stack-alertmanager -n monitoring 9093:9093`
   - Visit [`http://localhost:9093`](http://localhost:9093) to view the firing alert.
3. **Inspect SQS & Bedrock Processing**:
   - The alert triggers the SQS queue `boutique-aiops-alerts.fifo`.
   - The `aiops-assistant` pod ingests the message and invokes Amazon Bedrock Claude 3.5 Sonnet.
   - Tail assistant logs:
     ```bash
     kubectl logs -n boutique deployment/aiops-assistant -f
     ```
4. **Inspect DynamoDB RCA Report**:
   ```bash
   aws dynamodb scan --region us-east-2 --table-name boutique-aiops-rca-reports \
     --query 'Items[*].{ProposalID:proposal_id.S, Category:category.S, Status:status.S, Confidence:confidence_score.N}'
   ```
5. **Review and Approve via CLI**:
   ```bash
   python3 aiops/operator_cli.py list
   python3 aiops/operator_cli.py show <PROPOSAL_ID>
   python3 aiops/operator_cli.py approve <PROPOSAL_ID>
   ```
6. **Restore Baseline Replicas**:
   ```bash
   kubectl scale deployment auth -n boutique --replicas=1
   ```
