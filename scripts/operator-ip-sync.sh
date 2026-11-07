#!/usr/bin/env bash
# ==============================================================================
# Script: scripts/operator-ip-sync.sh
# Purpose: Dynamically update EKS publicAccessCidrs to operator's workstation IPv4 /32
# Security: Enforces least-privilege source IP allowlisting without 0.0.0.0/0 exposure
# ==============================================================================

set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-boutique-dev-eks}"
AWS_REGION="${AWS_REGION:-us-east-2}"
OVERRIDE_IP=""
ALLOW_ALL=false
CHECK_STATUS=false

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Synchronizes AWS EKS cluster API publicAccessCidrs with your current workstation IPv4 /32.

Options:
  -c, --cluster <name>    EKS cluster name (default: boutique-dev-eks)
  -r, --region <region>   AWS region (default: us-east-2)
  -i, --ip <ip>           Manually specify IPv4 address instead of auto-detection
  -s, --status            Print current EKS endpoint access configuration and exit
  --allow-all             Temporarily allow 0.0.0.0/0 (WARNING: insecure, dev only)
  -h, --help              Show this help message

Examples:
  ./scripts/operator-ip-sync.sh
  ./scripts/operator-ip-sync.sh --status
  ./scripts/operator-ip-sync.sh --ip 198.51.100.12
EOF
  exit 0
}

# Parse command line options
while [[ $# -gt 0 ]]; do
  case "$1" in
    -c|--cluster)
      CLUSTER_NAME="$2"
      shift 2
      ;;
    -r|--region)
      AWS_REGION="$2"
      shift 2
      ;;
    -i|--ip)
      OVERRIDE_IP="$2"
      shift 2
      ;;
    -s|--status)
      CHECK_STATUS=true
      shift
      ;;
    --allow-all)
      ALLOW_ALL=true
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "[-] Unknown option: $1" >&2
      usage
      ;;
  esac
done

# Prerequisite checks
for cmd in aws curl jq; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[-] Error: required command '$cmd' is not installed." >&2
    exit 1
  fi
done

# Query status if requested
if [[ "$CHECK_STATUS" == true ]]; then
  echo "[*] Querying endpoint configuration for cluster: ${CLUSTER_NAME} (${AWS_REGION})..."
  aws eks describe-cluster \
    --name "${CLUSTER_NAME}" \
    --region "${AWS_REGION}" \
    --query 'cluster.resourcesVpcConfig.{EndpointPublicAccess:endpointPublicAccess,EndpointPrivateAccess:endpointPrivateAccess,PublicAccessCidrs:publicAccessCidrs}' \
    --output json
  exit 0
fi

# Determine target CIDR
if [[ "$ALLOW_ALL" == true ]]; then
  TARGET_CIDR="0.0.0.0/0"
  echo "[!] WARNING: Configuring open publicAccessCidrs (0.0.0.0/0). Use only for temporary dev operations."
elif [[ -n "$OVERRIDE_IP" ]]; then
  if ! [[ "$OVERRIDE_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "[-] Error: Invalid IPv4 address format: ${OVERRIDE_IP}" >&2
    exit 1
  fi
  TARGET_CIDR="${OVERRIDE_IP}/32"
else
  echo "[*] Detecting current public workstation IPv4 address..."
  DETECTED_IP="$(curl -s --max-time 5 https://checkip.amazonaws.com 2>/dev/null || curl -s --max-time 5 https://icanhazip.com 2>/dev/null || true)"
  DETECTED_IP="$(echo "${DETECTED_IP}" | tr -d '[:space:]')"

  if ! [[ "$DETECTED_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "[-] Error: Failed to detect valid public IPv4 address. Received: '${DETECTED_IP}'" >&2
    echo "    Specify manually using: $0 --ip <YOUR_IP>" >&2
    exit 1
  fi
  TARGET_CIDR="${DETECTED_IP}/32"
fi

echo "[+] Target CIDR for EKS cluster '${CLUSTER_NAME}': ${TARGET_CIDR}"

# Fetch current CIDRs
CURRENT_CIDRS="$(aws eks describe-cluster \
  --name "${CLUSTER_NAME}" \
  --region "${AWS_REGION}" \
  --query 'cluster.resourcesVpcConfig.publicAccessCidrs' \
  --output json 2>/dev/null || echo "[]")"

echo "[*] Current cluster CIDRs: ${CURRENT_CIDRS}"

# Check if already matching
if echo "${CURRENT_CIDRS}" | jq -e --arg cidr "${TARGET_CIDR}" '. == [$cidr]' >/dev/null 2>&1; then
  echo "[✓] Cluster publicAccessCidrs is already set to ${TARGET_CIDR}. No AWS update required."
else
  echo "[*] Submitting EKS update-cluster-config to AWS..."
  UPDATE_OUT="$(aws eks update-cluster-config \
    --name "${CLUSTER_NAME}" \
    --region "${AWS_REGION}" \
    --resources-vpc-config "publicAccessCidrs=${TARGET_CIDR}" \
    --output json)"

  UPDATE_ID="$(echo "${UPDATE_OUT}" | jq -r '.update.id')"
  echo "[+] Cluster config update initiated. Update ID: ${UPDATE_ID}"
  echo "[*] Status: Updating cluster publicAccessCidrs to ${TARGET_CIDR}..."
fi

# Optional local dev.auto.tfvars sync (if present and ignored)
TFVARS_FILE="devops/terraform/environments/dev/dev.auto.tfvars"
if [[ -f "${TFVARS_FILE}" ]]; then
  if grep -q "admin_cidr_blocks" "${TFVARS_FILE}"; then
    echo "[*] Aligning local Git-ignored ${TFVARS_FILE} with ${TARGET_CIDR}..."
    sed -i.bak -E "s|admin_cidr_blocks\s*=\s*\[.*\]|admin_cidr_blocks = [\"${TARGET_CIDR}\"]|" "${TFVARS_FILE}"
    rm -f "${TFVARS_FILE}.bak"
    echo "[+] Updated ${TFVARS_FILE} successfully."
  fi
fi

echo "[✓] Operator IP sync completed successfully."
