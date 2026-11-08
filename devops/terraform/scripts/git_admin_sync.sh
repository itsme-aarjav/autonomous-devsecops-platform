#!/usr/bin/env bash
# Syncs local repository state to in-cluster Git daemon for offline/standby GitOps sync.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
NAMESPACE="argocd"
DEPLOYMENT="in-cluster-git"

if [ ! -d "$REPO_DIR/.git" ]; then
  echo "[-] Error: Repository directory not found: $REPO_DIR"
  exit 1
fi

COMMIT_SHA=$(git -C "$REPO_DIR" rev-parse HEAD)
BRANCH=$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD)

echo "[*] Authenticated Git Admin Sync"
echo "[*] Target Branch: $BRANCH ($COMMIT_SHA)"

# 1. Verify Kubernetes Authentication
if ! kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" >/dev/null 2>&1; then
  echo "[-] Error: Unable to authenticate to Kubernetes or deployment $DEPLOYMENT not found in $NAMESPACE"
  exit 1
fi

GIT_POD=$(kubectl get pods -n "$NAMESPACE" -l app="$DEPLOYMENT" -o jsonpath='{.items[0].metadata.name}')

# 2. Create Ephemeral Verified Bundle
TMP_BUNDLE="/tmp/git-sync-$COMMIT_SHA.bundle"
echo "[*] Generating Git bundle for $BRANCH..."
git -C "$REPO_DIR" bundle create "$TMP_BUNDLE" "$BRANCH"

# 3. Securely Transfer Bundle to in-cluster persistent storage via authenticated K8s API
echo "[*] Transferring bundle to pod $GIT_POD via authenticated Kubernetes API..."
kubectl cp "$TMP_BUNDLE" "$NAMESPACE/$GIT_POD:/tmp/admin-sync.bundle"
rm -f "$TMP_BUNDLE"

# 4. Ingest and Verify on Persistent Volume
echo "[*] Applying bundle to persistent Git repository..."
kubectl exec -n "$NAMESPACE" "$GIT_POD" -- sh -c "
  set -e
  git -C /git/boutique.git fetch -f /tmp/admin-sync.bundle 'refs/heads/$BRANCH:refs/heads/$BRANCH'
  git -C /git/boutique.git symbolic-ref HEAD refs/heads/$BRANCH
  rm -f /tmp/admin-sync.bundle
  echo '[+] Repository updated to: '\$(git -C /git/boutique.git rev-parse HEAD)
"

# 5. Refresh Argo CD Application
if kubectl get application boutique -n "$NAMESPACE" >/dev/null 2>&1; then
  echo "[*] Requesting Argo CD refresh..."
  kubectl patch application boutique -n "$NAMESPACE" --type merge -p "{\"operation\":{\"sync\":{\"revision\":\"$BRANCH\"}}}" >/dev/null 2>&1 || true
fi

echo "[+] Successfully synchronized revision $COMMIT_SHA via authenticated workflow."
