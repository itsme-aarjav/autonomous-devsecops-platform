#!/usr/bin/env bash
# Script: sync_secrets_to_k8s.sh
# Purpose: Synchronize all platform production secrets from AWS Secrets Manager
#          into target Kubernetes namespaces (boutique and monitoring).
#
# Target Secret Mappings:
#   1. AWS Secrets Manager: boutique/auth/jwt-secret
#      -> K8s Secret: boutique-jwt (namespace: boutique)
#         Key: JWT_SECRET
#
#   2. AWS Secrets Manager: boutique/database/credentials
#      -> K8s Secret: boutique-secrets (namespace: boutique)
#         Keys: POSTGRES_PASSWORD, AUTH_DB_URL
#
#   3. AWS Secrets Manager: boutique/aiops/webhook-token
#      -> K8s Secret: aiops-webhook-secret (namespaces: boutique AND monitoring)
#         Key: token (Synchronized identically across both namespaces)
#
#   4. AWS Secrets Manager: boutique/aiops/github-token (Optional)
#      -> K8s Secret: aiops-github-secret (namespace: boutique)
#         Key: token
#
# Security Invariants:
#   - Never prints secret values to stdout, stderr, logs, or command-line arguments.
#   - Avoids --from-literal to prevent secret leakage in system process tables (/proc).
#   - Uses restrictive temporary files (chmod 600 inside chmod 700 directory).
#   - Memory and temporary files wiped via shred/rm in EXIT, INT, and TERM trap handlers.
#   - Rejects weak, empty, or default placeholder secrets.

set -euo pipefail

DEFAULT_REGION="us-east-2"
DEFAULT_NAMESPACE="boutique"
DEFAULT_MONITORING_NAMESPACE="monitoring"
MIN_SECRET_LENGTH=16

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-$DEFAULT_REGION}}"
NAMESPACE="$DEFAULT_NAMESPACE"
MONITORING_NAMESPACE="$DEFAULT_MONITORING_NAMESPACE"

JWT_SECRET_NAME="boutique/auth/jwt-secret"
DB_SECRET_NAME="boutique/database/credentials"
WEBHOOK_SECRET_NAME="boutique/aiops/webhook-token"
GITHUB_SECRET_NAME="boutique/aiops/github-token"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Synchronizes production secrets from AWS Secrets Manager to Kubernetes Secrets.

Options:
  -n, --namespace <ns>              Target boutique namespace (default: ${DEFAULT_NAMESPACE})
  -m, --monitoring-namespace <ns>   Target monitoring namespace (default: ${DEFAULT_MONITORING_NAMESPACE})
  -r, --region <region>             AWS region (default: ${DEFAULT_REGION})
  -h, --help                        Show this help message
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    -m|--monitoring-namespace)
      MONITORING_NAMESPACE="$2"
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
# 2. Pre-flight AWS Account, Region & Cluster Identity Verification
# Fail closed: abort if any identity check fails before touching any secret.
# ------------------------------------------------------------------------------
EXPECTED_ACCOUNT="592668326948"
EXPECTED_REGION="us-east-2"
EXPECTED_CLUSTER="boutique-dev-eks"

echo "==> Verifying AWS caller identity..."
ACTUAL_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
if [[ "$ACTUAL_ACCOUNT" != "$EXPECTED_ACCOUNT" ]]; then
  echo "[ERROR] AWS account mismatch. Expected: ${EXPECTED_ACCOUNT}, Got: '${ACTUAL_ACCOUNT}'. Aborting." >&2
  exit 1
fi
echo "    [OK] AWS account verified: ${ACTUAL_ACCOUNT}"

echo "==> Verifying AWS region..."
if [[ "$REGION" != "$EXPECTED_REGION" ]]; then
  echo "[ERROR] Region mismatch. Expected: ${EXPECTED_REGION}, Got: '${REGION}'. Aborting." >&2
  exit 1
fi
echo "    [OK] AWS region verified: ${REGION}"

echo "==> Verifying Kubernetes context cluster..."
CURRENT_CLUSTER=$(kubectl config view --minify -o jsonpath='{.clusters[0].name}' 2>/dev/null || echo "")
if [[ "$CURRENT_CLUSTER" != *"${EXPECTED_CLUSTER}"* ]]; then
  echo "[ERROR] Kubernetes cluster mismatch. Expected context targeting '${EXPECTED_CLUSTER}', Got: '${CURRENT_CLUSTER}'. Aborting." >&2
  exit 1
fi
echo "    [OK] Kubernetes context cluster verified: ${CURRENT_CLUSTER}"

echo "==> Verifying EKS cluster identity via AWS API..."
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

if [[ -z "$EXPECTED_ENDPOINT" || -z "$EXPECTED_CA_DATA" ]]; then
  echo "[ERROR] Could not extract authoritative endpoint or CA data from AWS EKS describe-cluster. Aborting." >&2
  exit 1
fi

echo "==> Verifying Kubernetes context server endpoint and Certificate Authority..."
CURRENT_ENDPOINT=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null || echo "")
CURRENT_CA_DATA=$(kubectl config view --minify --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' 2>/dev/null || echo "")

if [[ -z "$CURRENT_ENDPOINT" ]]; then
  echo "[ERROR] Could not retrieve server endpoint from current kubectl context. Aborting." >&2
  exit 1
fi

EXPECTED_ENDPOINT_NORM="${EXPECTED_ENDPOINT%/}"
CURRENT_ENDPOINT_NORM="${CURRENT_ENDPOINT%/}"

if [[ "$CURRENT_ENDPOINT_NORM" != "$EXPECTED_ENDPOINT_NORM" ]]; then
  echo "[ERROR] Kubernetes API endpoint mismatch. Expected: '${EXPECTED_ENDPOINT_NORM}', Got: '${CURRENT_ENDPOINT_NORM}'. Aborting." >&2
  exit 1
fi
echo "    [OK] Kubernetes API endpoint verified: ${CURRENT_ENDPOINT_NORM}"

if [[ -n "$CURRENT_CA_DATA" ]]; then
  if [[ "$CURRENT_CA_DATA" != "$EXPECTED_CA_DATA" ]]; then
    echo "[ERROR] Kubernetes Certificate Authority data mismatch with AWS EKS cluster authoritative CA. Aborting." >&2
    exit 1
  fi
  echo "    [OK] Kubernetes Certificate Authority verified."
else
  CA_FILE=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.certificate-authority}' 2>/dev/null || echo "")
  if [[ -f "$CA_FILE" ]]; then
    LOCAL_CA_B64=$(base64 -i "$CA_FILE" 2>/dev/null | tr -d '\n' || base64 "$CA_FILE" 2>/dev/null | tr -d '\n' || echo "")
    if [[ "$LOCAL_CA_B64" != "$EXPECTED_CA_DATA" ]]; then
      echo "[ERROR] CA file content mismatch with AWS EKS cluster authoritative CA. Aborting." >&2
      exit 1
    fi
    echo "    [OK] Kubernetes Certificate Authority (file) verified."
  else
    echo "[ERROR] Neither inline certificate-authority-data nor valid certificate-authority file found in current kubectl context. Aborting." >&2
    exit 1
  fi
fi

# ------------------------------------------------------------------------------
# 3. Safe Temporary Workspace & Cleanup Trap Setup
# (Was section 2 — renumbered after pre-flight insertion)
# ------------------------------------------------------------------------------
TMP_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t 'k8s_secret_sync')
chmod 700 "$TMP_DIR"

cleanup() {
  if [[ -d "${TMP_DIR:-}" ]]; then
    if command -v shred >/dev/null 2>&1; then
      find "$TMP_DIR" -type f -exec shred -u -z {} + 2>/dev/null || true
    fi
    rm -rf "$TMP_DIR"
  fi
  # Unset sensitive variables
  unset RAW_JWT RAW_DB RAW_WEBHOOK RAW_GITHUB
  unset VAL_JWT VAL_DB_PASS VAL_DB_USER VAL_DB_URL VAL_WEBHOOK VAL_GITHUB
}
trap cleanup EXIT INT TERM

# Verify required namespaces exist — do NOT create them on an unverified cluster.
# Namespaces must be provisioned by Terraform/Helm before this script runs.
for ns in "$NAMESPACE" "$MONITORING_NAMESPACE"; do
  if ! kubectl get namespace "$ns" >/dev/null 2>&1; then
    echo "[ERROR] Required namespace '${ns}' does not exist. Provision it via Terraform/Helm before running this script." >&2
    exit 1
  fi
  echo "    [OK] Namespace '${ns}' exists."
done

# Helper: fetch secret payload safely
fetch_secret_payload() {
  local sname="$1"
  aws secretsmanager get-secret-value \
    --secret-id "$sname" \
    --region "$REGION" \
    --query "SecretString" \
    --output text 2>/dev/null || echo ""
}

# Helper: reject common insecure placeholders
check_placeholder() {
  local val="$1"
  local name="$2"
  case "$val" in
    "your-super-secret-jwt-key-here"|"your-secret-key"|"secret"|"changeme"|"password"|"default"|"admin"|"replace_with_a_secure_random_32_plus_char_secret_for_local_dev"|"replace-with-a-secure-random-32-plus-character-secret-in-production"|"postgres123")
      echo "[ERROR] Insecure or default placeholder secret detected for ${name}. Refusing to bootstrap." >&2
      return 1
      ;;
  esac
  return 0
}

# ==============================================================================
# 3. Synchronize Secret: boutique-jwt
# ==============================================================================
echo "==> Fetching '${JWT_SECRET_NAME}' from AWS Secrets Manager..."
RAW_JWT=$(fetch_secret_payload "$JWT_SECRET_NAME")
if [[ -z "$RAW_JWT" || "$RAW_JWT" == "None" ]]; then
  echo "[ERROR] Failed to retrieve '${JWT_SECRET_NAME}' or payload is empty." >&2
  exit 1
fi

VAL_JWT=$(echo "$RAW_JWT" | jq -e -r '.JWT_SECRET // empty' 2>/dev/null || echo "")
unset RAW_JWT
if [[ -z "$VAL_JWT" ]]; then
  echo "[ERROR] Key 'JWT_SECRET' is missing or empty in '${JWT_SECRET_NAME}'." >&2
  exit 1
fi
if ! check_placeholder "$VAL_JWT" "JWT_SECRET"; then exit 1; fi
if [[ "${#VAL_JWT}" -lt 32 ]]; then
  echo "[ERROR] JWT_SECRET does not meet minimum 32-character requirement (current: ${#VAL_JWT})." >&2
  exit 1
fi

FILE_JWT="${TMP_DIR}/JWT_SECRET"
printf "%s" "$VAL_JWT" > "$FILE_JWT"
chmod 600 "$FILE_JWT"
unset VAL_JWT

kubectl create secret generic boutique-jwt \
  --namespace "$NAMESPACE" \
  --from-file=JWT_SECRET="$FILE_JWT" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

echo "    [OK] Synchronized Kubernetes Secret 'boutique-jwt' (key: JWT_SECRET) in namespace '${NAMESPACE}'."

# ==============================================================================
# 4. Synchronize Secret: boutique-secrets (Database Credentials & Auth URL)
# ==============================================================================
echo "==> Fetching '${DB_SECRET_NAME}' from AWS Secrets Manager..."
RAW_DB=$(fetch_secret_payload "$DB_SECRET_NAME")
if [[ -z "$RAW_DB" || "$RAW_DB" == "None" ]]; then
  echo "[ERROR] Failed to retrieve '${DB_SECRET_NAME}' or payload is empty." >&2
  exit 1
fi

VAL_DB_USER=$(echo "$RAW_DB" | jq -e -r '.POSTGRES_USER // "postgres"' 2>/dev/null || echo "postgres")
VAL_DB_PASS=$(echo "$RAW_DB" | jq -e -r '.POSTGRES_PASSWORD // empty' 2>/dev/null || echo "")
unset RAW_DB

if [[ -z "$VAL_DB_PASS" ]]; then
  echo "[ERROR] Key 'POSTGRES_PASSWORD' is missing or empty in '${DB_SECRET_NAME}'." >&2
  exit 1
fi
if ! check_placeholder "$VAL_DB_PASS" "POSTGRES_PASSWORD"; then exit 1; fi
if [[ "${#VAL_DB_PASS}" -lt "$MIN_SECRET_LENGTH" ]]; then
  echo "[ERROR] POSTGRES_PASSWORD does not meet minimum ${MIN_SECRET_LENGTH}-character requirement." >&2
  exit 1
fi

# Formulate standard in-cluster connection string for the boutique database
VAL_DB_URL="postgresql://${VAL_DB_USER}:${VAL_DB_PASS}@postgres.${NAMESPACE}.svc.cluster.local:5432/auth_db"

FILE_DB_PASS="${TMP_DIR}/POSTGRES_PASSWORD"
FILE_DB_URL="${TMP_DIR}/AUTH_DB_URL"
printf "%s" "$VAL_DB_PASS" > "$FILE_DB_PASS"
printf "%s" "$VAL_DB_URL" > "$FILE_DB_URL"
chmod 600 "$FILE_DB_PASS" "$FILE_DB_URL"
unset VAL_DB_PASS VAL_DB_URL VAL_DB_USER

kubectl create secret generic boutique-secrets \
  --namespace "$NAMESPACE" \
  --from-file=POSTGRES_PASSWORD="$FILE_DB_PASS" \
  --from-file=AUTH_DB_URL="$FILE_DB_URL" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

echo "    [OK] Synchronized Kubernetes Secret 'boutique-secrets' (keys: POSTGRES_PASSWORD, AUTH_DB_URL) in namespace '${NAMESPACE}'."

# ==============================================================================
# 5. Synchronize Secret: aiops-webhook-secret (Both boutique and monitoring)
# ==============================================================================
echo "==> Fetching '${WEBHOOK_SECRET_NAME}' from AWS Secrets Manager..."
RAW_WEBHOOK=$(fetch_secret_payload "$WEBHOOK_SECRET_NAME")
if [[ -z "$RAW_WEBHOOK" || "$RAW_WEBHOOK" == "None" ]]; then
  echo "[ERROR] Failed to retrieve '${WEBHOOK_SECRET_NAME}' or payload is empty." >&2
  exit 1
fi

VAL_WEBHOOK=$(echo "$RAW_WEBHOOK" | jq -e -r '.token // empty' 2>/dev/null || echo "")
unset RAW_WEBHOOK
if [[ -z "$VAL_WEBHOOK" ]]; then
  echo "[ERROR] Key 'token' is missing or empty in '${WEBHOOK_SECRET_NAME}'." >&2
  exit 1
fi
if ! check_placeholder "$VAL_WEBHOOK" "aiops-webhook-token"; then exit 1; fi

FILE_WEBHOOK="${TMP_DIR}/token"
printf "%s" "$VAL_WEBHOOK" > "$FILE_WEBHOOK"
chmod 600 "$FILE_WEBHOOK"
unset VAL_WEBHOOK

# Synchronize identically to boutique namespace (for AIOps assistant receiver)
kubectl create secret generic aiops-webhook-secret \
  --namespace "$NAMESPACE" \
  --from-file=token="$FILE_WEBHOOK" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

# Synchronize identically to monitoring namespace (for Alertmanager HTTP bearer auth)
kubectl create secret generic aiops-webhook-secret \
  --namespace "$MONITORING_NAMESPACE" \
  --from-file=token="$FILE_WEBHOOK" \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null

echo "    [OK] Synchronized Kubernetes Secret 'aiops-webhook-secret' (key: token) across namespaces '${NAMESPACE}' and '${MONITORING_NAMESPACE}'."

# ==============================================================================
# 6. Synchronize Secret: aiops-github-secret (Optional / Graceful)
# ==============================================================================
RAW_GITHUB=$(fetch_secret_payload "$GITHUB_SECRET_NAME")
if [[ -n "$RAW_GITHUB" && "$RAW_GITHUB" != "None" ]]; then
  VAL_GITHUB=$(echo "$RAW_GITHUB" | jq -e -r '.token // empty' 2>/dev/null || echo "")
  unset RAW_GITHUB
  if [[ -n "$VAL_GITHUB" && "$VAL_GITHUB" != "null" ]]; then
    FILE_GITHUB="${TMP_DIR}/github_token"
    printf "%s" "$VAL_GITHUB" > "$FILE_GITHUB"
    chmod 600 "$FILE_GITHUB"
    unset VAL_GITHUB

    kubectl create secret generic aiops-github-secret \
      --namespace "$NAMESPACE" \
      --from-file=token="$FILE_GITHUB" \
      --dry-run=client -o yaml | kubectl apply -f - >/dev/null

    echo "    [OK] Synchronized Kubernetes Secret 'aiops-github-secret' (key: token) in namespace '${NAMESPACE}'."
  fi
else
  echo "    [NOTICE] Secret '${GITHUB_SECRET_NAME}' is unseeded; skipping optional 'aiops-github-secret'."
fi

echo "==> All required Kubernetes secrets successfully synchronized from AWS Secrets Manager."
