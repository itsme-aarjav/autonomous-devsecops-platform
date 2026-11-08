#!/usr/bin/env bash
# Sync JWT via server-side apply without exposing secret values.

set -euo pipefail

DEFAULT_REGION="us-east-2"
DEFAULT_SECRET_NAME="boutique/auth/jwt-secret"
DEFAULT_NAMESPACE="boutique"
FIELD_MANAGER="devops-secret-sync"
MIN_SECRET_LENGTH=32

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-$DEFAULT_REGION}}"
SECRET_NAME="$DEFAULT_SECRET_NAME"
NAMESPACE="$DEFAULT_NAMESPACE"
AUTHORIZED="${AUTHORIZE_SECRET_SYNC:-false}"
DRY_RUN="false"
EXPECTED_ACCOUNT="592668326948"
EXPECTED_REGION="us-east-2"
EXPECTED_CLUSTER="boutique-dev-eks"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Synchronizes JWT_SECRET from AWS Secrets Manager to Kubernetes Secret 'boutique-jwt' via Server-Side Apply.

Options:
  -n, --namespace <ns>    Target Kubernetes namespace (default: ${DEFAULT_NAMESPACE})
  -s, --secret-name <name> AWS Secrets Manager secret name (default: ${DEFAULT_SECRET_NAME})
  -r, --region <region>   AWS region (default: ${DEFAULT_REGION})
  -a, --authorized        Explicit human authorization to read Secrets Manager
      --dry-run           Pre-validate identity, metadata, and inputs without writing to K8s
  -h, --help              Show this help message
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--namespace)
      NAMESPACE="${2:-}"
      shift 2
      ;;
    -s|--secret-name)
      SECRET_NAME="${2:-}"
      shift 2
      ;;
    -r|--region)
      REGION="${2:-}"
      shift 2
      ;;
    -a|--authorized)
      AUTHORIZED="true"
      shift
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "[ERROR] Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$AUTHORIZED" != "true" ]]; then
  echo "[ERROR] Explicit human authorization required to synchronize secrets from AWS Secrets Manager." >&2
  echo "        Pass --authorized or set AUTHORIZE_SECRET_SYNC=true to proceed under Stage 3C approval." >&2
  exit 1
fi

# 1. Prerequisite Validation & Pre-flight Identity Check
for tool in aws jq kubectl; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "[ERROR] Required prerequisite '$tool' is not installed or not in PATH." >&2
    exit 1
  fi
done

echo "==> [Pre-flight] Verifying AWS caller identity..."
ACTUAL_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
if [[ "$ACTUAL_ACCOUNT" != "$EXPECTED_ACCOUNT" ]]; then
  echo "[ERROR] AWS account mismatch. Expected: ${EXPECTED_ACCOUNT}, Got: '${ACTUAL_ACCOUNT}'. Aborting." >&2
  exit 1
fi
echo "    [OK] AWS account verified: ${ACTUAL_ACCOUNT}"

echo "==> [Pre-flight] Verifying AWS region..."
if [[ "$REGION" != "$EXPECTED_REGION" ]]; then
  echo "[ERROR] Region mismatch. Expected: ${EXPECTED_REGION}, Got: '${REGION}'. Aborting." >&2
  exit 1
fi
echo "    [OK] AWS region verified: ${REGION}"

echo "==> [Pre-flight] Verifying Kubernetes context cluster..."
CURRENT_CLUSTER=$(kubectl config view --minify -o jsonpath='{.clusters[0].name}' 2>/dev/null || echo "")
if [[ "$CURRENT_CLUSTER" != *"${EXPECTED_CLUSTER}"* ]]; then
  echo "[ERROR] Kubernetes cluster mismatch. Expected context targeting '${EXPECTED_CLUSTER}', Got: '${CURRENT_CLUSTER}'. Aborting." >&2
  exit 1
fi
echo "    [OK] Kubernetes context cluster verified: ${CURRENT_CLUSTER}"

echo "==> [Pre-flight] Verifying EKS cluster identity via AWS API..."
EKS_DESCRIBE=$(aws eks describe-cluster --name "${EXPECTED_CLUSTER}" --region "${EXPECTED_REGION}" --output json 2>/dev/null || echo "")
if [[ -z "$EKS_DESCRIBE" ]]; then
  echo "[ERROR] Failed to describe EKS cluster '${EXPECTED_CLUSTER}' via AWS API in region '${EXPECTED_REGION}'. Aborting." >&2
  exit 1
fi

EKS_CLUSTER_STATUS=$(echo "$EKS_DESCRIBE" | jq -r '.cluster.status // empty' 2>/dev/null || echo "")
if [[ "$EKS_CLUSTER_STATUS" != "ACTIVE" ]]; then
  echo "[ERROR] EKS cluster '${EXPECTED_CLUSTER}' is not ACTIVE in AWS (status: '${EKS_CLUSTER_STATUS}'). Aborting." >&2
  exit 1
fi
echo "    [OK] EKS cluster status: ACTIVE"

EXPECTED_ENDPOINT=$(echo "$EKS_DESCRIBE" | jq -r '.cluster.endpoint // empty' 2>/dev/null || echo "")
EXPECTED_CA_DATA=$(echo "$EKS_DESCRIBE" | jq -r '.cluster.certificateAuthority.data // empty' 2>/dev/null || echo "")
CURRENT_ENDPOINT=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null || echo "")
CURRENT_CA_DATA=$(kubectl config view --minify --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' 2>/dev/null || echo "")

if [[ -z "$CURRENT_ENDPOINT" || "${CURRENT_ENDPOINT%/}" != "${EXPECTED_ENDPOINT%/}" ]]; then
  echo "[ERROR] Kubernetes API endpoint mismatch. Expected: '${EXPECTED_ENDPOINT}', Got: '${CURRENT_ENDPOINT}'. Aborting." >&2
  exit 1
fi
if [[ -n "$CURRENT_CA_DATA" && "$CURRENT_CA_DATA" != "$EXPECTED_CA_DATA" ]]; then
  echo "[ERROR] Kubernetes Certificate Authority data mismatch with AWS EKS cluster authoritative CA. Aborting." >&2
  exit 1
fi
echo "    [OK] Kubernetes API endpoint and Certificate Authority verified."

echo "==> [Pre-flight] Verifying target Kubernetes namespace '${NAMESPACE}'..."
if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
  echo "[ERROR] Target namespace '${NAMESPACE}' does not exist on cluster. Provision it before synchronizing." >&2
  exit 1
fi
echo "    [OK] Target namespace '${NAMESPACE}' exists."

# 2. Pre-validate Secret Metadata (Existence & AWSCURRENT)
echo "==> Pre-validating secret metadata for '${SECRET_NAME}'..."
META=$(aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$REGION" --output json 2>/dev/null || echo "")
if [[ -z "$META" ]]; then
  echo "[ERROR] AWS Secrets Manager object '${SECRET_NAME}' does not exist or access was denied." >&2
  exit 1
fi

DELETED_DATE=$(echo "$META" | jq -r '.DeletedDate // empty' 2>/dev/null || echo "")
if [[ -n "$DELETED_DATE" ]]; then
  echo "[ERROR] AWS Secrets Manager object '${SECRET_NAME}' is scheduled for deletion (${DELETED_DATE}). Refusing to read." >&2
  exit 1
fi

HAS_CURRENT=$(echo "$META" | jq -r '(.VersionIdsToStages // {}) | to_entries[] | select(.value[] == "AWSCURRENT") | .key' 2>/dev/null || echo "")
if [[ -z "$HAS_CURRENT" ]]; then
  echo "[ERROR] AWS Secrets Manager object '${SECRET_NAME}' has no 'AWSCURRENT' version stage (container is unseeded)." >&2
  exit 1
fi
echo "    [OK] Secret '${SECRET_NAME}' metadata verified: active and contains AWSCURRENT version."

# 3. Retrieve Secret from AWS Secrets Manager
echo "==> Fetching secret '${SECRET_NAME}' from AWS Secrets Manager (${REGION})..."
RAW_PAYLOAD=""
if ! RAW_PAYLOAD=$(aws secretsmanager get-secret-value \
    --secret-id "$SECRET_NAME" \
    --region "$REGION" \
    --query "SecretString" \
    --output text 2>/dev/null); then
  echo "[ERROR] Failed to retrieve '${SECRET_NAME}' from AWS Secrets Manager in region '${REGION}'." >&2
  exit 1
fi

if [[ -z "$RAW_PAYLOAD" || "$RAW_PAYLOAD" == "None" ]]; then
  echo "[ERROR] Retrieved SecretString is empty or null from AWS Secrets Manager." >&2
  exit 1
fi

# 4. Extract and Validate JWT_SECRET
JWT_SECRET=""
if ! JWT_SECRET=$(echo "$RAW_PAYLOAD" | jq -e -r '.JWT_SECRET // empty' 2>/dev/null); then
  echo "[ERROR] Failed to parse JSON or 'JWT_SECRET' key is missing from secret payload." >&2
  exit 1
fi
unset RAW_PAYLOAD

if [[ -z "$JWT_SECRET" ]]; then
  echo "[ERROR] Extracted JWT_SECRET is empty." >&2
  exit 1
fi

case "$JWT_SECRET" in
  "your-super-secret-jwt-key-here"|"your-secret-key"|"secret"|"changeme"|"password"|"default"|"admin"|"replace_with_a_secure_random_32_plus_char_secret_for_local_dev"|"replace-with-a-secure-random-32-plus-character-secret-in-production")
    echo "[ERROR] Insecure or default placeholder secret detected. Refusing to synchronize." >&2
    unset JWT_SECRET
    exit 1
    ;;
esac

SECRET_LEN="${#JWT_SECRET}"
if [[ "$SECRET_LEN" -lt "$MIN_SECRET_LENGTH" ]]; then
  echo "[ERROR] JWT_SECRET does not meet minimum production length requirement (${MIN_SECRET_LENGTH} characters)." >&2
  unset JWT_SECRET
  exit 1
fi
echo "    [OK] JWT secret payload validated successfully in memory (${SECRET_LEN} bytes)."

# 5. Safe Temporary File Handling & Trap Setup
TMP_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t 'jwt_sync')
chmod 700 "$TMP_DIR"
SECRET_FILE="${TMP_DIR}/JWT_SECRET"

cleanup() {
  if [[ -d "${TMP_DIR:-}" ]]; then
    if command -v shred >/dev/null 2>&1 && [[ -f "$SECRET_FILE" ]]; then
      shred -u -z "$SECRET_FILE" 2>/dev/null || rm -f "$SECRET_FILE"
    fi
    rm -rf "$TMP_DIR"
  fi
  unset JWT_SECRET
}
trap cleanup EXIT INT TERM

printf "%s" "$JWT_SECRET" > "$SECRET_FILE"
chmod 600 "$SECRET_FILE"
unset JWT_SECRET

# 6. Apply to Kubernetes as Secret 'boutique-jwt' via Server-Side Apply
if [[ "$DRY_RUN" == "true" ]]; then
  echo "    [DRY-RUN] Validated Server-Side Apply payload for Secret 'boutique-jwt' in namespace '${NAMESPACE}' (write skipped)."
  exit 0
fi

echo "==> Applying Kubernetes Secret 'boutique-jwt' in namespace '${NAMESPACE}' via Server-Side Apply..."
if ! kubectl create secret generic boutique-jwt \
    --namespace "$NAMESPACE" \
    --from-file=JWT_SECRET="$SECRET_FILE" \
    --dry-run=client -o yaml | \
  kubectl apply --server-side --field-manager="${FIELD_MANAGER}" -f - >/dev/null; then
  echo "[ERROR] Failed to apply Secret 'boutique-jwt' via Server-Side Apply in namespace '${NAMESPACE}'." >&2
  exit 1
fi

echo "==> [OK] Secret 'boutique-jwt' successfully synchronized to namespace '${NAMESPACE}' via Server-Side Apply."
