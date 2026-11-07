# Terminal Outputs & Verification Logs

This directory contains real, reproducible command-line verification outputs captured by evaluators and automated tests.

## Suggested Evidence Outputs

- **`01-cluster-nodes-pods.txt`**: Output of `kubectl get nodes -o wide` and `kubectl get pods -n boutique -o wide`.
- **`02-commerce-api-test.txt`**: Output of the end-to-end e-commerce tests (products, cart, checkout, order history, inventory locking).
- **`03-aiops-cli-session.txt`**: Terminal transcript of running `python3 aiops/operator_cli.py list`, `show`, `approve`, `reject`.
- **`04-backup-restore-log.txt`**: Log output proving successful isolated restoration of EBS snapshot `snap-05a3b0ffe3463e280`.
