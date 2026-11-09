# AIOps Operator Workflow

This guide explains how a human reviewed and approved AI-assisted fixes in the **historical AWS demo**. The live SQS queues, DynamoDB tables and EKS cluster have since been removed.

## What happened

```text
Prometheus alert → Alertmanager → SQS FIFO → AIOps diagnosis (Bedrock Nova Lite)
→ DynamoDB proposal → operator review → approval or rejection
→ GitHub PR → human merge → Argo CD deployment
```

The assistant gathered evidence and suggested a bounded memory change. It could not directly edit the running cluster.

## Operator commands

The repository contains [`aiops/operator_cli.py`](../aiops/operator_cli.py) with these actions:

| Action | Purpose |
| --- | --- |
| `list` | Find proposals awaiting review |
| `show <proposal-id>` | Read the root cause, policy result and YAML diff |
| `approve <proposal-id>` | Authenticate, approve and create a pull request |
| `reject <proposal-id> --reason "..."` | Reject the proposal with an audit reason |
| `status <proposal-id>` | Check the recorded proposal status |

During live verification, the first unsuitable proposal was rejected. A later canary proposal was approved after its diff showed a memory change from `64Mi/128Mi` to `256Mi/512Mi`. See [approval proof](terminal-outputs/30-aiops-human-approval-pr.txt) and [PR #2](https://github.com/itsme-aarjav/autonomous-devsecops-platform/pull/2).

## Safety and testing

- The operator identity and approval token were checked.
- Only allowlisted changes could pass the policy check.
- GitHub PR review and merge were required before Argo CD could reconcile the change.
- Local test fixtures can exercise CLI safety paths without AWS. **They are not proof of a live Bedrock invocation.**

For the actual incident, use the [live terminal evidence](terminal-outputs/README.md). Do not run historical production approval commands against the deleted environment.
