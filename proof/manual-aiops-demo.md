# AIOps Remediation & Operator CLI Guide

This guide explains the human-in-the-loop remediation workflow and operator CLI commands used to review and approve incident proposals.

---

## 1. Remediation Lifecycle Flow

```
Prometheus Alert (Pod OOMKilled)
       │
       ▼
Amazon SQS FIFO Queue (`boutique-aiops-alert-queue.fifo`)
       │
       ▼
AIOps Reasoning Agent (LangGraph + Amazon Bedrock Nova Lite)
       │
       ▼
Deterministic Policy Check & DynamoDB Proposal Storage
       │
       ▼
Cloud Operator Review via CLI (`python3 aiops/operator_cli.py`)
       │
       ├─► Reject (Logs rejection reason in DynamoDB audit trail)
       │
       └─► Approve (Validates HMAC token, opens reviewed GitHub PR)
              │
              ▼
       Human Review & Merge to `main`
              │
              ▼
       Argo CD Automatic Reconciliation on Cluster
```

---

## 2. Safety Invariants & Guardrails

1. **Two-Stage Architecture**:
   - **Stage 1 (Automated Diagnostics)**: Reads cluster events, pods, and Prometheus metrics; sanitizes sensitive tokens; generates structured RCA with Amazon Bedrock Nova Lite.
   - **Stage 2 (Human Approval)**: Autonomous direct writes to `main` are blocked. Remediation proposals require explicit human approval before a Pull Request is opened.
2. **Deterministic Policy Bounds**:
   - Only allowlisted operations pass policy (e.g., container memory limit bumps between `128Mi` and `1024Mi`, replica scaling between `1` and `5`).
   - Destructive actions (such as `rm -rf`, `DROP TABLE`, or deleting pods/nodes) are automatically blocked.
3. **Constant-Time Authentication**:
   - The CLI verifies operator identity using `hmac.compare_digest` against authorized tokens, protecting against timing attacks.

---

## 3. Operator CLI Commands

Operators manage pending remediation proposals using `aiops/operator_cli.py`:

### A. List Pending Proposals
```bash
# View proposals awaiting operator review
python3 aiops/operator_cli.py list --status pending
```

### B. Inspect Proposal Details & Manifest Diff
```bash
# Inspect root cause diagnosis, policy badge, and surgical manifest diff
python3 aiops/operator_cli.py show <PROPOSAL_ID>
```

### C. Reject a Proposal
```bash
# Reject a proposal and record operator audit reasoning in DynamoDB
python3 aiops/operator_cli.py reject <PROPOSAL_ID> --reason "Investigating alternative workload optimization"
```

### D. Approve a Proposal (Opens GitHub Pull Request)
```bash
# Authenticate with operator token and open a reviewed GitHub Pull Request
python3 aiops/operator_cli.py approve <PROPOSAL_ID>
```

---

## 4. Offline Simulation Mode for Local Verification

Because active AWS infrastructure has been decommissioned, developers and evaluators can verify the complete CLI workflow offline using hermetic simulation fixtures:

```bash
# 1. List simulated pending proposals
python3 aiops/operator_cli.py list --simulate

# 2. Inspect a simulated proposal and diff
python3 aiops/operator_cli.py show sim-prop-001 --simulate

# 3. Test operator rejection
python3 aiops/operator_cli.py reject sim-prop-001 --simulate --reason "Testing rejection flow"
```

---

## 5. Correlating Live Verification Logs

The live execution of this workflow on AWS EKS was captured in the following terminal outputs:
- [`16-aiops-human-review.txt`](terminal-outputs/16-aiops-human-review.txt): Operator listing and inspecting pending proposals in CloudShell.
- [`17-aiops-human-rejection.txt`](terminal-outputs/17-aiops-human-rejection.txt): Operator exercising the rejection path with audit reasoning.
- [`29-aiops-approval-review.txt`](terminal-outputs/29-aiops-approval-review.txt): Operator reviewing fresh canary OOM incident proposal.
- [`30-aiops-human-approval-pr.txt`](terminal-outputs/30-aiops-human-approval-pr.txt): Operator HMAC approval opening reviewed GitHub Pull Request.
- [`32-aiops-gitops-pr-merge.txt`](terminal-outputs/32-aiops-gitops-pr-merge.txt): Reviewed Pull Request merged into `main`.
- [`33-aiops-gitops-deployment.txt`](terminal-outputs/33-aiops-gitops-deployment.txt): Argo CD automatic reconciliation and workload recovery.
