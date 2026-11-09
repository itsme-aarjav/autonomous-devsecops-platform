# AIOps Assistant

This Python service helps investigate Kubernetes incidents. During the live AWS demo, it received alerts, collected cluster evidence, used **Amazon Bedrock Nova Lite** for root cause analysis (RCA), and prepared possible GitOps fixes. **A human had to approve a fix before a pull request was opened.**

The AWS demo has since been decommissioned; these are the implemented workflows and historical verification records.

## How an incident is processed

1. **Alert intake:** Alertmanager sends an event to an Amazon SQS FIFO queue.
2. **Validation:** The assistant checks and normalizes the alert, including duplicate handling.
3. **Evidence collection:** It gathers relevant Kubernetes events, logs and monitoring data.
4. **Sanitization:** Sensitive values are removed before model inference.
5. **Diagnosis:** Amazon Bedrock Nova Lite (`amazon.nova-lite-v1:0`) returns a structured RCA.
6. **Storage:** DynamoDB stores incident information, reports and remediation proposals.
7. **Policy check:** Allowed changes are checked against predefined limits.
8. **Operator review:** The CLI shows the diagnosis and manifest diff. Approval opens a GitHub pull request; rejection records the decision.

### LangGraph steps

The graph in [`agent/graph.py`](agent/graph.py) contains eight main nodes:

```text
validate_input → normalize_incident → collect_evidence → sanitize_evidence
→ analyze_with_bedrock → validate_rca → persist_result → propose_remediation
```

The graph also has conditional paths for errors and duplicate or resolved incidents. The eight steps are a diagnostic workflow; they do **not** give the AI permission to edit the cluster directly.

## Human approval and safety

The [operator CLI](operator_cli.py) can list, inspect, approve and reject proposals. It checks the operator's authorization and approval token. The remediation code limits which files and resource settings can be changed and uses a GitHub PR rather than writing directly to `main`.

The verified OOMKilled example changed the **test canary** memory request from `64Mi` to `256Mi` and the limit from `128Mi` to `512Mi`. See [PR #2](https://github.com/itsme-aarjav/autonomous-devsecops-platform/pull/2).

## Tests and evidence

From the repository root, run:

```bash
python3 -m unittest discover -s aiops/tests -p "test_*.py" -v
```

The recorded regression suite contains **27 tests** covering approval safety and canary remediation. Local unit-test fixtures are separate from the historical **live AWS Bedrock** incident.

- [AIOps pipeline explanation](../proof/architecture/aiops-pipeline.md)
- [Human approval and PR evidence](../proof/terminal-outputs/30-aiops-human-approval-pr.txt)
- [Operator rejection evidence](../proof/terminal-outputs/17-aiops-human-rejection.txt)
- [AIOps log index](../proof/terminal-outputs/README.md)
