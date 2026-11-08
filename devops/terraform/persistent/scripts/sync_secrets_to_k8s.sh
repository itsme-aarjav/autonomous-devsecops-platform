#!/usr/bin/env bash
# ==============================================================================
# Script: sync_secrets_to_k8s.sh
# Purpose: Synchronize scoped production secrets from AWS Secrets Manager
#          into target Kubernetes namespaces using Server-Side Apply.
#
# Supported Scopes:
#   Scope A: webhook (--scope webhook) [Stage 3B.3A]
#     AWS Source: boutique/aiops/webhook-token (key: token)
#     K8s Targets:
#       - monitoring/aiops-webhook-secret
#       - boutique/aiops-webhook-secret
#     Security Boundary: Never accesses or reads historical DB/JWT or GitHub secrets.
#
#   Scope B: app (--scope app) [Stage 3C]
#     AWS Sources:
#       - boutique/auth/jwt-secret (key: JWT_SECRET)
#       - boutique/database/credentials (keys: POSTGRES_PASSWORD, AUTH_DB_URL)
#     K8s Targets:
#       - boutique/boutique-jwt
#       - boutique/boutique-secrets
#     Security Boundary: Never accesses or reads webhook, approval, or GitHub tokens.
#
#   Scope C: github (--scope github)
#     AWS Source: boutique/aiops/github-token
#     Security Boundary: Excluded from default sync. Fails closed without future authorization.
#
# Security & Operational Invariants:
#   - Enforces Server-Side Apply (--server-side --field-manager=devops-secret-sync)
#     to eliminate client-side last-applied annotations containing base64 secret data.
#   - Pre-validates all source metadata and values in memory before touching Kubernetes.
#   - Fails closed on missing scope, unseeded secret containers, or missing AWSCURRENT versions.
#   - All-or-nothing write semantics: Zero Kubernetes Secrets written if any prerequisite fails.
#   - Never outputs secret values to stdout, stderr, process tables (/proc), or logs.
#   - Restrictive temporary file permissions (chmod 600 in chmod 700 dir) with shred/rm trap.
# ==============================================================================

set -euo pipefail

DEFAULT_REGION="us-east-2"
DEFAULT_NAMESPACE="boutique"
DEFAULT_MONITORING_NAMESPACE="monitoring"
FIELD_MANAGER="devops-secret-sync"

MIN_SECRET_LENGTH=16
MIN_JWT_LENGTH=32

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-$DEFAULT_REGION}}"
NAMESPACE="$DEFAULT_NAMESPACE"
MONITORING_NAMESPACE="$DEFAULT_MONITORING_NAMESPACE"

JWT_SECRET_NAME="boutique/auth/jwt-secret"
DB_SECRET_NAME="boutique/database/credentials"
WEBHOOK_SECRET_NAME="boutique/aiops/webhook-token"
GITHUB_SECRET_NAME="boutique/aiops/github-token"

SCOPE=""
AUTHORIZED="${AUTHORIZE_SECRET_SYNC:-false}"
DRY_RUN="false"

usage() {
  cat <<EOF
Usage: $(basename "$0") --scope <webhook|app|github> [OPTIONS]

Synchronizes scoped secrets from AWS Secrets Manager to Kubernetes Secrets using Server-Side Apply.

Required:
  -s, --scope <scope>               Synchronization scope:
                                      'webhook' - AIOps webhook token (monitoring & boutique) [Stage 3B.3A]
                                      'app'     - Application JWT & Database credentials [Stage 3C]
                                      'github'  - GitHub token (excluded by default, fails closed)

Options:
  -n, --namespace <ns>              Target boutique namespace (default: ${DEFAULT_NAMESPACE})
  -m, --monitoring-namespace <ns>   Target monitoring namespace (default: ${DEFAULT_MONITORING_NAMESPACE})
  -r, --region <region>             AWS region (default: ${DEFAULT_REGION})
  -a, --authorized                  Explicit human authorization to access Secrets Manager
      --dry-run                     Pre-validate identity, metadata, and inputs without writing to K8s
  -h, --help                        Show this help message
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--scope)
      SCOPE="${2:-}"
      shift 2
      ;;
    -n|--namespace)
      NAMESPACE="${2:-}"
      shift 2
      ;;
    -m|--monitoring-namespace)
      MONITORING_NAMESPACE="${2:-}"
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

# ------------------------------------------------------------------------------
# 1. Scope and Authorization Validation (Fail-Closed)
# ------------------------------------------------------------------------------
if [[ -z "$SCOPE" ]]; then
  echo "[ERROR] Mandatory parameter '--scope <webhook|app|github>' is missing." >&2
  echo "        Secret synchronization requires an explicit scope. Run '$(basename "$0") --help' for details." >&2
  exit 1
fi

case "$SCOPE" in
  webhook|aiops-webhook)
    SCOPE="webhook"
    ;;
  app|application)
    SCOPE="app"
    ;;
  github)
    echo "[ERROR] Scope 'github' (boutique/aiops/github-token) is excluded from default synchronization." >&2
    echo "        Automated remediation tokens require separate future authorization. Aborting." >&2
    exit 1
    ;;
  *)
    echo "[ERROR] Invalid scope: '${SCOPE}'. Allowed values: 'webhook', 'app'." >&2
    exit 1
    ;;
esac

if [[ "$AUTHORIZED" != "true" ]]; then
  echo "[ERROR] Explicit human authorization required to synchronize secrets from AWS Secrets Manager." >&2
  echo "        Pass '--authorized' or set 'AUTHORIZE_SECRET_SYNC=true' following explicit approval." >&2
  exit 1
fi

# ------------------------------------------------------------------------------
# 2. Prerequisite Tools Check
# ------------------------------------------------------------------------------
for tool in aws jq kubectl python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "[ERROR] Required prerequisite '$tool' is not installed or not in PATH." >&2
    exit 1
  fi
done

# ------------------------------------------------------------------------------
# 3. Pre-flight AWS Account, Region & Cluster Identity Verification
# ------------------------------------------------------------------------------
EXPECTED_ACCOUNT="592668326948"
EXPECTED_REGION="us-east-2"
EXPECTED_CLUSTER="boutique-dev-eks"

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

if [[ -z "$EXPECTED_ENDPOINT" || -z "$EXPECTED_CA_DATA" ]]; then
  echo "[ERROR] Could not extract authoritative endpoint or CA data from AWS EKS describe-cluster. Aborting." >&2
  exit 1
fi

echo "==> [Pre-flight] Verifying Kubernetes context server endpoint and Certificate Authority..."
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
# 4. Target Namespace Verification
# ------------------------------------------------------------------------------
REQUIRED_NAMESPACES=()
if [[ "$SCOPE" == "webhook" ]]; then
  REQUIRED_NAMESPACES=("$NAMESPACE" "$MONITORING_NAMESPACE")
elif [[ "$SCOPE" == "app" ]]; then
  REQUIRED_NAMESPACES=("$NAMESPACE")
fi

echo "==> [Pre-flight] Verifying required Kubernetes namespaces exist..."
for ns in "${REQUIRED_NAMESPACES[@]}"; do
  if ! kubectl get namespace "$ns" >/dev/null 2>&1; then
    echo "[ERROR] Required namespace '${ns}' does not exist on cluster. Provision it via Terraform before synchronizing." >&2
    exit 1
  fi
  echo "    [OK] Namespace '${ns}' exists."
done

# ------------------------------------------------------------------------------
# 5. Safe Temporary Workspace & Cleanup Trap Setup
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
  # Unset all sensitive variables from memory
  unset RAW_PAYLOAD VAL_JWT VAL_DB_USER VAL_DB_PASS VAL_DB_URL VAL_WEBHOOK
}
trap cleanup EXIT INT TERM

# ------------------------------------------------------------------------------
# 6. Helper Functions
# ------------------------------------------------------------------------------
check_secret_metadata_has_current() {
  local sname="$1"
  local meta
  meta=$(aws secretsmanager describe-secret --secret-id "$sname" --region "$REGION" --output json 2>/dev/null || echo "")
  if [[ -z "$meta" ]]; then
    echo "[ERROR] AWS Secrets Manager object '${sname}' does not exist or access was denied." >&2
    return 1
  fi

  local deleted_date
  deleted_date=$(echo "$meta" | jq -r '.DeletedDate // empty' 2>/dev/null || echo "")
  if [[ -n "$deleted_date" ]]; then
    echo "[ERROR] AWS Secrets Manager object '${sname}' is scheduled for deletion (${deleted_date}). Refusing to read." >&2
    return 1
  fi

  local has_current
  has_current=$(echo "$meta" | jq -r '(.VersionIdsToStages // {}) | to_entries[] | select(.value[] == "AWSCURRENT") | .key' 2>/dev/null || echo "")
  if [[ -z "$has_current" ]]; then
    echo "[ERROR] AWS Secrets Manager object '${sname}' has no 'AWSCURRENT' version stage (container is unseeded)." >&2
    echo "        A secret version must be seeded in AWS Secrets Manager before synchronization." >&2
    return 1
  fi
  return 0
}

fetch_secret_payload() {
  local sname="$1"
  aws secretsmanager get-secret-value \
    --secret-id "$sname" \
    --region "$REGION" \
    --query "SecretString" \
    --output text 2>/dev/null || echo ""
}

check_placeholder() {
  local val="$1"
  local name="$2"
  case "$val" in
    "your-super-secret-jwt-key-here"|"your-secret-key"|"secret"|"changeme"|"password"|"default"|"admin"|"replace_with_a_secure_random_32_plus_char_secret_for_local_dev"|"replace-with-a-secure-random-32-plus-character-secret-in-production"|"postgres123")
      echo "[ERROR] Insecure or default placeholder secret detected for ${name}. Refusing to synchronize." >&2
      return 1
      ;;
  esac
  return 0
}

apply_secret_ssa() {
  local secret_name="$1"
  local target_ns="$2"
  shift 2
  local from_file_args=("$@")

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "    [DRY-RUN] Validated Server-Side Apply payload for Secret '${secret_name}' in namespace '${target_ns}' (write skipped)."
    return 0
  fi

  # Apply via Server-Side Apply with dedicated field manager.
  # This avoids kubectl.kubernetes.io/last-applied-configuration annotation containing secret data.
  kubectl create secret generic "$secret_name" \
    --namespace "$target_ns" \
    "${from_file_args[@]}" \
    --dry-run=client -o yaml | \
  kubectl apply --server-side --field-manager="${FIELD_MANAGER}" -f - >/dev/null

  echo "    [OK] Synchronized Kubernetes Secret '${secret_name}' via Server-Side Apply in namespace '${target_ns}'."
}

# ==============================================================================
# SCOPE A: AIOps Webhook Token Synchronization (Stage 3B.3A)
# ==============================================================================
if [[ "$SCOPE" == "webhook" ]]; then
  echo "==> [Scope A: Webhook] Pre-validating secret metadata for '${WEBHOOK_SECRET_NAME}'..."
  if ! check_secret_metadata_has_current "$WEBHOOK_SECRET_NAME"; then
    echo "[ERROR] Pre-validation failed for '${WEBHOOK_SECRET_NAME}'. Stage 3B.3A is BLOCKED pending token seeding." >&2
    echo "        ZERO Kubernetes Secrets were written." >&2
    exit 1
  fi
  echo "    [OK] Metadata verified: '${WEBHOOK_SECRET_NAME}' is active and has an AWSCURRENT version."

  echo "==> [Scope A: Webhook] Fetching and validating secret payload in memory..."
  RAW_PAYLOAD=$(fetch_secret_payload "$WEBHOOK_SECRET_NAME")
  if [[ -z "$RAW_PAYLOAD" || "$RAW_PAYLOAD" == "None" ]]; then
    echo "[ERROR] Failed to retrieve '${WEBHOOK_SECRET_NAME}' or payload is empty. Refusing to write." >&2
    exit 1
  fi

  VAL_WEBHOOK=$(echo "$RAW_PAYLOAD" | jq -e -r '.token // empty' 2>/dev/null || echo "")
  unset RAW_PAYLOAD

  if [[ -z "$VAL_WEBHOOK" ]]; then
    echo "[ERROR] Key 'token' is missing or empty in '${WEBHOOK_SECRET_NAME}'. Refusing to write." >&2
    exit 1
  fi
  if ! check_placeholder "$VAL_WEBHOOK" "aiops-webhook-token"; then exit 1; fi
  if [[ "${#VAL_WEBHOOK}" -lt "$MIN_SECRET_LENGTH" ]]; then
    echo "[ERROR] Webhook token does not meet minimum ${MIN_SECRET_LENGTH}-character requirement (current: ${#VAL_WEBHOOK})." >&2
    exit 1
  fi

  FILE_WEBHOOK="${TMP_DIR}/token"
  printf "%s" "$VAL_WEBHOOK" > "$FILE_WEBHOOK"
  chmod 600 "$FILE_WEBHOOK"
  unset VAL_WEBHOOK

  echo "    [OK] Webhook token payload validated successfully in memory."

  echo "==> [Scope A: Webhook] Applying Kubernetes Secrets using Server-Side Apply..."
  # 1. Monitoring namespace (for Alertmanager HTTP bearer auth)
  apply_secret_ssa "aiops-webhook-secret" "$MONITORING_NAMESPACE" "--from-file=token=${FILE_WEBHOOK}"

  # 2. Boutique namespace (for AIOps assistant receiver)
  apply_secret_ssa "aiops-webhook-secret" "$NAMESPACE" "--from-file=token=${FILE_WEBHOOK}"

  echo "==> [Scope A: Webhook] Successfully synchronized 'aiops-webhook-secret' across '${MONITORING_NAMESPACE}' and '${NAMESPACE}'."
  exit 0
fi

# ==============================================================================
# SCOPE B: Application Credentials (JWT & Database) (Stage 3C)
# ==============================================================================
if [[ "$SCOPE" == "app" ]]; then
  echo "==> [Scope B: App] Pre-validating secret metadata for '${JWT_SECRET_NAME}' and '${DB_SECRET_NAME}'..."
  if ! check_secret_metadata_has_current "$JWT_SECRET_NAME"; then
    echo "[ERROR] Pre-validation failed for '${JWT_SECRET_NAME}'. ZERO Kubernetes Secrets were written." >&2
    exit 1
  fi
  if ! check_secret_metadata_has_current "$DB_SECRET_NAME"; then
    echo "[ERROR] Pre-validation failed for '${DB_SECRET_NAME}'. ZERO Kubernetes Secrets were written." >&2
    exit 1
  fi
  echo "    [OK] Metadata verified: Both secrets are active and have AWSCURRENT versions."

  echo "==> [Scope B: App] Fetching and validating JWT payload in memory..."
  RAW_PAYLOAD=$(fetch_secret_payload "$JWT_SECRET_NAME")
  if [[ -z "$RAW_PAYLOAD" || "$RAW_PAYLOAD" == "None" ]]; then
    echo "[ERROR] Failed to retrieve '${JWT_SECRET_NAME}' or payload is empty. Refusing to write." >&2
    exit 1
  fi

  VAL_JWT=$(echo "$RAW_PAYLOAD" | jq -e -r '.JWT_SECRET // empty' 2>/dev/null || echo "")
  unset RAW_PAYLOAD

  if [[ -z "$VAL_JWT" ]]; then
    echo "[ERROR] Key 'JWT_SECRET' is missing or empty in '${JWT_SECRET_NAME}'. Refusing to write." >&2
    exit 1
  fi
  if ! check_placeholder "$VAL_JWT" "JWT_SECRET"; then exit 1; fi
  if [[ "${#VAL_JWT}" -lt "$MIN_JWT_LENGTH" ]]; then
    echo "[ERROR] JWT_SECRET does not meet minimum ${MIN_JWT_LENGTH}-character requirement (current: ${#VAL_JWT})." >&2
    exit 1
  fi

  FILE_JWT="${TMP_DIR}/JWT_SECRET"
  printf "%s" "$VAL_JWT" > "$FILE_JWT"
  chmod 600 "$FILE_JWT"
  unset VAL_JWT
  echo "    [OK] JWT secret payload validated successfully in memory."

  echo "==> [Scope B: App] Fetching and validating Database credentials in memory..."
  RAW_PAYLOAD=$(fetch_secret_payload "$DB_SECRET_NAME")
  if [[ -z "$RAW_PAYLOAD" || "$RAW_PAYLOAD" == "None" ]]; then
    echo "[ERROR] Failed to retrieve '${DB_SECRET_NAME}' or payload is empty. Refusing to write." >&2
    exit 1
  fi

  VAL_DB_USER=$(echo "$RAW_PAYLOAD" | jq -e -r '.POSTGRES_USER // "postgres"' 2>/dev/null || echo "postgres")
  VAL_DB_PASS=$(echo "$RAW_PAYLOAD" | jq -e -r '.POSTGRES_PASSWORD // empty' 2>/dev/null || echo "")
  unset RAW_PAYLOAD

  if [[ -z "$VAL_DB_PASS" ]]; then
    echo "[ERROR] Key 'POSTGRES_PASSWORD' is missing or empty in '${DB_SECRET_NAME}'. Refusing to write." >&2
    exit 1
  fi
  if ! check_placeholder "$VAL_DB_PASS" "POSTGRES_PASSWORD"; then exit 1; fi
  if [[ "${#VAL_DB_PASS}" -lt "$MIN_SECRET_LENGTH" ]]; then
    echo "[ERROR] POSTGRES_PASSWORD does not meet minimum ${MIN_SECRET_LENGTH}-character requirement (current: ${#VAL_DB_PASS})." >&2
    exit 1
  fi

  FILE_DB_PASS="${TMP_DIR}/POSTGRES_PASSWORD"
  printf "%s" "$VAL_DB_PASS" > "$FILE_DB_PASS"
  chmod 600 "$FILE_DB_PASS"

  # Safely formulate URL-encoded connection string via stdin python pipe to prevent /proc leakage
  ENCODED_USER=$(printf "%s" "$VAL_DB_USER" | python3 -c "import urllib.parse, sys; sys.stdout.write(urllib.parse.quote_plus(sys.stdin.read()))")
  ENCODED_PASS=$(python3 -c "import urllib.parse, sys; sys.stdout.write(urllib.parse.quote_plus(sys.stdin.read()))" < "$FILE_DB_PASS")
  VAL_DB_URL="postgresql://${ENCODED_USER}:${ENCODED_PASS}@boutique-postgres.${NAMESPACE}.svc.cluster.local:5432/auth_db"

  FILE_DB_URL="${TMP_DIR}/AUTH_DB_URL"
  printf "%s" "$VAL_DB_URL" > "$FILE_DB_URL"
  chmod 600 "$FILE_DB_URL"
  unset VAL_DB_PASS VAL_DB_URL VAL_DB_USER ENCODED_USER ENCODED_PASS
  echo "    [OK] Database credentials validated successfully in memory."

  echo "==> [Scope B: App] Applying Kubernetes Secrets using Server-Side Apply..."
  # 1. Secret: boutique-jwt
  apply_secret_ssa "boutique-jwt" "$NAMESPACE" "--from-file=JWT_SECRET=${FILE_JWT}"

  # 2. Secret: boutique-secrets
  apply_secret_ssa "boutique-secrets" "$NAMESPACE" \
    "--from-file=POSTGRES_PASSWORD=${FILE_DB_PASS}" \
    "--from-file=AUTH_DB_URL=${FILE_DB_URL}"

  echo "==> [Scope B: App] Successfully synchronized 'boutique-jwt' and 'boutique-secrets' in namespace '${NAMESPACE}'."
  exit 0
fi

echo "[ERROR] Unhandled scope condition. Aborting." >&2
exit 1
