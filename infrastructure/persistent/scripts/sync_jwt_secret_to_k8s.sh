#!/usr/bin/env bash
# ==============================================================================
# Script: sync_jwt_secret_to_k8s.sh
# Purpose: Securely bootstrap or synchronize JWT_SECRET from AWS Secrets Manager
#          into the Kubernetes Secret 'boutique-jwt' for Boutique microservices.
#
# Source of Truth:
#   AWS Secrets Manager: boutique/auth/jwt-secret
# Target:
#   Kubernetes Secret:   boutique-jwt (key: JWT_SECRET)
#
# Operational Prerequisites:
#   - AWS CLI installed and configured with permissions:
#       secretsmanager:GetSecretValue on boutique/auth/jwt-secret
#       kms:Decrypt on the CMK (alias/boutique-aiops-key)
#   - jq installed
#   - kubectl installed and authenticated to target Kubernetes cluster
#   - Target namespace existing or permission to create it
#
# Security Invariants:
#   - Never prints secret values to stdout, stderr, logs, or command line arguments.
#   - Avoids --from-literal to prevent secret leakage in system process tables (/proc).
#   - Uses restrictive temporary files (chmod 600 in chmod 700 dir) safely cleaned up via trap.
#   - Rejects weak, empty, or < 32-character secrets.
#   - Manual synchronization model: operator must re-run upon AWS secret rotation
#     and restart dependent workloads (auth, gateway).
# ==============================================================================

set -euo pipefail

DEFAULT_REGION="us-east-2"
DEFAULT_SECRET_NAME="boutique/auth/jwt-secret"
DEFAULT_NAMESPACE="boutique"
MIN_SECRET_LENGTH=32

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-$DEFAULT_REGION}}"
SECRET_NAME="$DEFAULT_SECRET_NAME"
NAMESPACE="$DEFAULT_NAMESPACE"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Synchronizes JWT_SECRET from AWS Secrets Manager to Kubernetes Secret 'boutique-jwt'.

Options:
  -n, --namespace <ns>    Target Kubernetes namespace (default: ${DEFAULT_NAMESPACE})
  -s, --secret-name <name> AWS Secrets Manager secret name (default: ${DEFAULT_SECRET_NAME})
  -r, --region <region>   AWS region (default: ${DEFAULT_REGION})
  -h, --help              Show this help message
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    -s|--secret-name)
      SECRET_NAME="$2"
      shift 2
      ;;
    -r|--region)
      REGION="$2"
      shift 2
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

# ------------------------------------------------------------------------------
# 1. Prerequisite Validation
# ------------------------------------------------------------------------------
for tool in aws jq kubectl; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "[ERROR] Required prerequisite '$tool' is not installed or not in PATH." >&2
    exit 1
  fi
done

# ------------------------------------------------------------------------------
# 2. Retrieve Secret from AWS Secrets Manager
# ------------------------------------------------------------------------------
echo "==> Fetching secret '${SECRET_NAME}' from AWS Secrets Manager (${REGION})..."
RAW_PAYLOAD=""
if ! RAW_PAYLOAD=$(aws secretsmanager get-secret-value \
    --secret-id "$SECRET_NAME" \
    --region "$REGION" \
    --query "SecretString" \
    --output text 2>/dev/null); then
  echo "[ERROR] Failed to retrieve '${SECRET_NAME}' from AWS Secrets Manager in region '${REGION}'." >&2
  echo "        Verify AWS credentials, region, and IAM permissions (secretsmanager:GetSecretValue, kms:Decrypt)." >&2
  exit 1
fi

if [[ -z "$RAW_PAYLOAD" || "$RAW_PAYLOAD" == "None" ]]; then
  echo "[ERROR] Retrieved SecretString is empty or null from AWS Secrets Manager." >&2
  exit 1
fi

# ------------------------------------------------------------------------------
# 3. Extract and Validate JWT_SECRET
# ------------------------------------------------------------------------------
JWT_SECRET=""
if ! JWT_SECRET=$(echo "$RAW_PAYLOAD" | jq -e -r '.JWT_SECRET // empty' 2>/dev/null); then
  echo "[ERROR] Failed to parse JSON or 'JWT_SECRET' key is missing from secret payload." >&2
  exit 1
fi

# Clear raw payload from memory
unset RAW_PAYLOAD

if [[ -z "$JWT_SECRET" ]]; then
  echo "[ERROR] Extracted JWT_SECRET is empty." >&2
  exit 1
fi

case "$JWT_SECRET" in
  "your-super-secret-jwt-key-here"|"your-secret-key"|"secret"|"changeme"|"password"|"default"|"admin"|"replace_with_a_secure_random_32_plus_char_secret_for_local_dev"|"replace-with-a-secure-random-32-plus-character-secret-in-production")
    echo "[ERROR] Insecure or default placeholder secret detected. Refusing to bootstrap." >&2
    unset JWT_SECRET
    exit 1
    ;;
esac

SECRET_LEN="${#JWT_SECRET}"
if [[ "$SECRET_LEN" -lt "$MIN_SECRET_LENGTH" ]]; then
  echo "[ERROR] JWT_SECRET does not meet minimum production length requirements." >&2
  echo "        Current length: ${SECRET_LEN} characters. Minimum required: ${MIN_SECRET_LENGTH}." >&2
  unset JWT_SECRET
  exit 1
fi

# ------------------------------------------------------------------------------
# 4. Safe Temporary File Handling & Trap Setup
# ------------------------------------------------------------------------------
TMP_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t 'jwt_sync')
chmod 700 "$TMP_DIR"
SECRET_FILE="${TMP_DIR}/JWT_SECRET"

cleanup() {
  if [[ -d "${TMP_DIR:-}" ]]; then
    # Overwrite file contents before directory removal (standard overwrite pass; note modern SSDs manage wear-leveling)
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

# ------------------------------------------------------------------------------
# 5. Apply to Kubernetes as Secret 'boutique-jwt'
# ------------------------------------------------------------------------------
echo "==> Ensuring target Kubernetes namespace '${NAMESPACE}' exists..."
if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
  echo "    Namespace '${NAMESPACE}' not found. Creating..."
  kubectl create namespace "$NAMESPACE" >/dev/null
fi

echo "==> Applying Kubernetes Secret 'boutique-jwt' in namespace '${NAMESPACE}'..."
if ! kubectl create secret generic boutique-jwt \
    --namespace "$NAMESPACE" \
    --from-file=JWT_SECRET="$SECRET_FILE" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null; then
  echo "[ERROR] Failed to apply Secret 'boutique-jwt' to Kubernetes namespace '${NAMESPACE}'." >&2
  exit 1
fi

echo "==> Secret 'boutique-jwt' successfully synchronized to namespace '${NAMESPACE}'."
echo "    Key: JWT_SECRET (${SECRET_LEN} bytes, non-empty, validated)"
echo "    Workloads may now consume boutique-jwt via secretKeyRef."
