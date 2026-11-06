#!/usr/bin/env bash
# Promotes a microservice container image by immutable ECR digest directly to main with operator approval.
set -euo pipefail

APPROVED=false
if [ "${PROMOTION_APPROVED:-}" = "true" ] || [ "${PROMOTION_APPROVED:-}" = "1" ] || [ "${PROMOTION_APPROVED:-}" = "yes" ]; then
  APPROVED=true
fi

POSITIONAL_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --approve)
      APPROVED=true
      ;;
    *)
      POSITIONAL_ARGS+=("$arg")
      ;;
  esac
done

SERVICE="${POSITIONAL_ARGS[0]:-}"
TAG_OR_DIGEST="${POSITIONAL_ARGS[1]:-}"
AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-2}}"

if [ -z "$SERVICE" ] || [ -z "$TAG_OR_DIGEST" ]; then
  echo "Usage: $0 [--approve] <service-name> <tag-or-sha256-digest>"
  echo "Example: $0 auth 1842a74e --approve"
  echo "Example: $0 frontend sha256:f30a29202e498b331bc43b85be0f1219f846a6a8206a274d8e53097291b4d04f --approve"
  exit 1
fi

# Verify strict single-main-branch operational policy
CURRENT_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [ "$CURRENT_BRANCH" != "main" ]; then
  echo "Error: Direct-main promotions must run on the 'main' branch (current: '${CURRENT_BRANCH}'). Single-main-branch policy strictly enforced." >&2
  exit 1
fi

# Resolve ECR Registry dynamically or via ECR_REGISTRY override
if [ -n "${ECR_REGISTRY:-}" ]; then
  if [[ ! "$ECR_REGISTRY" =~ ^([0-9]{12})\.dkr\.ecr\.([a-z0-9-]+)\.amazonaws\.com$ ]]; then
    echo "Error: Invalid ECR_REGISTRY format: '$ECR_REGISTRY'. Expected '<account>.dkr.ecr.<region>.amazonaws.com'" >&2
    exit 1
  fi
  ACCOUNT_ID="${BASH_REMATCH[1]}"
  REGISTRY_REGION="${BASH_REMATCH[2]}"
  if [ "$REGISTRY_REGION" != "$AWS_REGION" ]; then
    echo "Warning: ECR_REGISTRY region ($REGISTRY_REGION) differs from AWS_REGION ($AWS_REGION). Using $REGISTRY_REGION." >&2
    AWS_REGION="$REGISTRY_REGION"
  fi
else
  ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
  if [[ ! "$ACCOUNT_ID" =~ ^[0-9]{12}$ ]]; then
    echo "Error: Failed to obtain valid 12-digit AWS account ID via STS. Set ECR_REGISTRY or configure active AWS credentials." >&2
    exit 1
  fi
  ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
fi

FALLBACK_MANIFEST=""
case "$SERVICE" in
  auth|boutique-auth)
    MANIFEST="devops/gitops/k8s/backend/auth.yml"
    REPO_NAME="boutique-auth"
    ;;
  gateway|boutique-gateway)
    MANIFEST="devops/gitops/k8s/backend/gateway.yml"
    REPO_NAME="boutique-gateway"
    ;;
  frontend|boutique-frontend)
    if [ -f "devops/gitops/k8s/frontend/rollout.yaml" ]; then
      MANIFEST="devops/gitops/k8s/frontend/rollout.yaml"
    else
      MANIFEST="devops/gitops/k8s/frontend/blue-green.yml"
      FALLBACK_MANIFEST="devops/gitops/k8s/frontend/deployment.yml"
    fi
    REPO_NAME="boutique-frontend"
    ;;
  *)
    echo "Error: Unknown service $SERVICE. Valid services are: auth, gateway, frontend." >&2
    exit 1
    ;;
esac

if [ ! -f "$MANIFEST" ]; then
  echo "Error: Manifest not found: $MANIFEST" >&2
  exit 1
fi

TARGET_MANIFESTS=("$MANIFEST")
if [ -n "$FALLBACK_MANIFEST" ]; then
  if [ ! -f "$FALLBACK_MANIFEST" ]; then
    echo "Error: Fallback manifest not found: $FALLBACK_MANIFEST" >&2
    exit 1
  fi
  TARGET_MANIFESTS+=("$FALLBACK_MANIFEST")
fi

# Protect pre-existing target manifest changes by failing fast if uncommitted changes exist or git status fails
if ! DIRTY_TARGETS=$(git status --porcelain -- "${TARGET_MANIFESTS[@]}"); then
  echo "Error: Failed to determine git status for target manifest(s): ${TARGET_MANIFESTS[*]}" >&2
  exit 1
fi
if [ -n "$DIRTY_TARGETS" ]; then
  echo "Error: Target manifest(s) have uncommitted (staged or unstaged) changes:" >&2
  echo "$DIRTY_TARGETS" >&2
  echo "Aborting promotion to protect pre-existing target manifest changes." >&2
  exit 1
fi

# Record pre-existing state and initialize cleanup trap before creating temporary resources
MANIFESTS_MODIFIED=false
PROMOTION_SUCCESS=false
SCAN_JSON=""
SCAN_JSON_CREATED=false
PROMOTION_MANIFEST=""
PROMOTION_MANIFEST_CREATED=false
REPORTS_DIR_PREEXISTED=false
[ -d "reports/promotions" ] && REPORTS_DIR_PREEXISTED=true
REPORTS_PARENT_PREEXISTED=false
[ -d "reports" ] && REPORTS_PARENT_PREEXISTED=true
SNAPSHOT_DIR=""

cleanup() {
  local exit_code=$?
  if [ "$PROMOTION_SUCCESS" != "true" ]; then
    echo "Promotion halted. Cleaning up local workspace..." >&2

    # Unstage ONLY promotion files from the index, preserving unrelated staged files
    local files_to_unstage=()
    [ ${#TARGET_MANIFESTS[@]} -gt 0 ] && files_to_unstage+=("${TARGET_MANIFESTS[@]}")
    [ -n "$PROMOTION_MANIFEST" ] && files_to_unstage+=("$PROMOTION_MANIFEST")
    [ -n "$SCAN_JSON" ] && files_to_unstage+=("$SCAN_JSON")
    if [ ${#files_to_unstage[@]} -gt 0 ]; then
      git reset --quiet HEAD -- "${files_to_unstage[@]}" 2>/dev/null || true
    fi

    # Restore target manifests on disk to exact pre-modification snapshot
    if [ "$MANIFESTS_MODIFIED" = "true" ] && [ -n "${SNAPSHOT_DIR:-}" ] && [ -d "$SNAPSHOT_DIR" ]; then
      for m in "${TARGET_MANIFESTS[@]}"; do
        if [ -f "$SNAPSHOT_DIR/$m" ]; then
          cp "$SNAPSHOT_DIR/$m" "$m"
        fi
      done
    fi

    # Remove generated report files ONLY if created by this promotion run
    if [ "$PROMOTION_MANIFEST_CREATED" = "true" ] && [ -e "$PROMOTION_MANIFEST" ]; then
      rm -f "$PROMOTION_MANIFEST"
    fi
    if [ "$SCAN_JSON_CREATED" = "true" ] && [ -e "$SCAN_JSON" ]; then
      rm -f "$SCAN_JSON"
    fi

    # Remove reports directories ONLY if created by this run and empty
    if [ "$REPORTS_DIR_PREEXISTED" = "false" ] && [ -d "reports/promotions" ]; then
      rmdir reports/promotions 2>/dev/null || true
    fi
    if [ "$REPORTS_PARENT_PREEXISTED" = "false" ] && [ -d "reports" ]; then
      rmdir reports 2>/dev/null || true
    fi
  fi

  # Always clean up the temp snapshot directory
  if [ -n "${SNAPSHOT_DIR:-}" ] && [ -d "$SNAPSHOT_DIR" ]; then
    rm -rf "$SNAPSHOT_DIR"
  fi
  exit "$exit_code"
}
trap cleanup EXIT

# Snapshot target manifests before any modifications
TMP_BASE="${TMPDIR:-/tmp}"
TMP_BASE="${TMP_BASE%/}"
SNAPSHOT_DIR=$(mktemp -d "${TMP_BASE}/promote_snapshot.XXXXXX")
for m in "${TARGET_MANIFESTS[@]}"; do
  mkdir -p "$SNAPSHOT_DIR/$(dirname "$m")"
  cp "$m" "$SNAPSHOT_DIR/$m"
done

# 1. Resolve exact immutable digest from ECR
if [[ "$TAG_OR_DIGEST" == sha256:* ]]; then
  DIGEST="$TAG_OR_DIGEST"
  if ! aws ecr describe-images --registry-id "$ACCOUNT_ID" --repository-name "$REPO_NAME" --image-ids imageDigest="$DIGEST" --region "$AWS_REGION" >/dev/null 2>&1; then
    echo "Error: Image digest $DIGEST does not exist in ECR repository $REPO_NAME (registry: $ACCOUNT_ID, region: $AWS_REGION)" >&2
    exit 1
  fi
  TAG="digest-promoted"
else
  TAG="$TAG_OR_DIGEST"
  DIGEST=$(aws ecr describe-images --registry-id "$ACCOUNT_ID" --repository-name "$REPO_NAME" --image-ids imageTag="$TAG" --region "$AWS_REGION" --query "imageDetails[0].imageDigest" --output text 2>/dev/null || echo "")
  if [ -z "$DIGEST" ] || [ "$DIGEST" = "None" ]; then
    echo "Error: Tag $TAG does not exist in ECR repository $REPO_NAME (registry: $ACCOUNT_ID, region: $AWS_REGION)" >&2
    exit 1
  fi
fi

SHORT_DIGEST=$(echo "$DIGEST" | cut -c8-19)
FULL_IMAGE_URI="${ECR_REGISTRY}/${REPO_NAME}@${DIGEST}"

echo "Resolved ECR Image: $FULL_IMAGE_URI"

# 2. In-memory preflight validation of all target manifests before modifying files or creating reports
echo "Preflighting target manifest(s) for ${REPO_NAME}..."
PREFLIGHT_OUTPUT=$(python3 devops/scripts/update_gitops_image.py \
  --dry-run \
  --manifest "${TARGET_MANIFESTS[@]}" \
  --service "$REPO_NAME" \
  --image-uri "$FULL_IMAGE_URI")
echo "$PREFLIGHT_OUTPUT"

# Verify at least one target manifest actually requires an update
if ! echo "$PREFLIGHT_OUTPUT" | grep -q "Would update:"; then
  echo "Error: None of the target manifests (${TARGET_MANIFESTS[*]}) changed; image URI $FULL_IMAGE_URI is already pinned across all target manifests." >&2
  exit 1
fi

# Protect existing report files: abort if output report filenames already exist
SCAN_JSON="reports/promotions/trivy-${SERVICE}-${SHORT_DIGEST}.json"
PROMOTION_MANIFEST="reports/promotions/release-${SERVICE}-${SHORT_DIGEST}.json"

if [ -e "$SCAN_JSON" ]; then
  echo "Error: Promotion scan report already exists: $SCAN_JSON. Refusing to overwrite existing report." >&2
  exit 1
fi

if [ -e "$PROMOTION_MANIFEST" ]; then
  echo "Error: Promotion manifest record already exists: $PROMOTION_MANIFEST. Refusing to overwrite existing record." >&2
  exit 1
fi

# Mark report ownership so cleanup safely deletes any partial or complete files created by this run
SCAN_JSON_CREATED=true
PROMOTION_MANIFEST_CREATED=true

# 3. Run Trivy vulnerability scan gate
echo "Executing Trivy vulnerability gate for $FULL_IMAGE_URI..."
mkdir -p reports/promotions
trivy image --severity HIGH,CRITICAL --format json --output "$SCAN_JSON" "$FULL_IMAGE_URI"
trivy image --severity HIGH,CRITICAL --exit-code 1 "$FULL_IMAGE_URI"

# 4. Create release manifest record
cat <<EOF > "$PROMOTION_MANIFEST"
{
  "service": "$SERVICE",
  "repository": "$REPO_NAME",
  "registry": "$ECR_REGISTRY",
  "tag": "$TAG",
  "digest": "$DIGEST",
  "image_uri": "$FULL_IMAGE_URI",
  "manifest_path": "$MANIFEST",
  "fallback_manifest_path": "${FALLBACK_MANIFEST:-none}",
  "promoted_at": "$(date -u +'%Y-%m-%dT%H:%M:%SZ')",
  "promoted_by": "$(git config user.name || echo 'Release Engineer')",
  "trivy_scan_gate": "PASSED (0 High, 0 Critical)"
}
EOF

# 5. Require Explicit Operator Approval before applying changes to main
if [ "$APPROVED" != "true" ]; then
  echo "Error: Explicit operator approval required to apply changes to 'main'." >&2
  echo "Pass '--approve' or set PROMOTION_APPROVED=true to approve and commit directly to 'main'." >&2
  exit 1
fi

# 6. Apply change directly to main working tree (NO branch creation)
MANIFESTS_MODIFIED=true
python3 devops/scripts/update_gitops_image.py --manifest "${TARGET_MANIFESTS[@]}" --service "$REPO_NAME" --image-uri "$FULL_IMAGE_URI"

# Verify at least one target manifest actually changed
if git diff --quiet "${TARGET_MANIFESTS[@]}"; then
  echo "Error: None of the target manifests (${TARGET_MANIFESTS[*]}) changed; image URI $FULL_IMAGE_URI is already pinned across all target manifests." >&2
  exit 1
fi

# 7. Validate with Kustomize
kubectl kustomize devops/gitops/ > /dev/null

# 8. Commit directly to local main branch (NO silent push, NO PR creation)
git add -- "${TARGET_MANIFESTS[@]}"
git add -f -- "$PROMOTION_MANIFEST" "$SCAN_JSON"
FILES_TO_ADD=("${TARGET_MANIFESTS[@]}" "$PROMOTION_MANIFEST" "$SCAN_JSON")
git commit "${FILES_TO_ADD[@]}" -m "chore(gitops): pin ${SERVICE} to immutable digest ${SHORT_DIGEST}"

PROMOTION_SUCCESS=true
echo "Promotion applied and committed locally to 'main' for ${SERVICE} (@${SHORT_DIGEST})."
echo "Target manifests validated with Kustomize."
echo "Notice: Changes were committed locally to 'main'. Push manually when ready: git push origin main"
