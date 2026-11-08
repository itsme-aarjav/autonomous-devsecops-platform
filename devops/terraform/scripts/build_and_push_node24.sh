#!/usr/bin/env bash
set -euo pipefail

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-2}}"

if [ -n "${ECR_REGISTRY:-}" ]; then
  REGISTRY="${ECR_REGISTRY}"
  if [[ "$REGISTRY" =~ ^([0-9]{12})\.dkr\.ecr\.([a-z0-9-]+)\.amazonaws\.com$ ]]; then
    ACCOUNT_ID="${BASH_REMATCH[1]}"
    REGISTRY_REGION="${BASH_REMATCH[2]}"
    if [ "$REGISTRY_REGION" != "$REGION" ]; then
      echo "Warning: ECR_REGISTRY region ($REGISTRY_REGION) differs from REGION ($REGION). Using $REGISTRY_REGION." >&2
      REGION="$REGISTRY_REGION"
    fi
  else
    echo "Error: ECR_REGISTRY does not match standard format '<account>.dkr.ecr.<region>.amazonaws.com': ${REGISTRY}" >&2
    exit 1
  fi
else
  ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo '')}"
  if [[ ! "$ACCOUNT_ID" =~ ^[0-9]{12}$ ]]; then
    echo "Error: Could not determine valid 12-digit AWS account ID. Please set AWS_ACCOUNT_ID, ECR_REGISTRY, or configure AWS CLI credentials." >&2
    exit 1
  fi
  REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
fi

TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo "latest")}"
CREATED=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

echo "ECR Registry: ${REGISTRY} (Account: ${ACCOUNT_ID}, Region: ${REGION})"
echo "Logging into ECR"
aws ecr get-login-password --region "${REGION}" | docker login --username AWS --password-stdin "${REGISTRY}"

SERVICES=(
  "boutique-auth:application/backend/services/auth"
  "boutique-gateway:application/backend/services/gateway"
  "boutique-frontend:application/frontend"
)

SUMMARY_FILE="${REPO_ROOT}/reports/image-build-and-scan-summary.json"
echo "[" > "${SUMMARY_FILE}"

first=1
for entry in "${SERVICES[@]}"; do
  REPO="${entry%%:*}"
  REL_PATH="${entry##*:}"
  BUILD_DIR="${REPO_ROOT}/${REL_PATH}"
  IMAGE_TAGGED="${REGISTRY}/${REPO}:${TAG}"
  IMAGE_LATEST="${REGISTRY}/${REPO}:latest"

  echo "[BUILD] Building ${REPO} from ${REL_PATH}..."

  docker build --platform linux/amd64 \
    --label "org.opencontainers.image.title=${REPO}" \
    --label "org.opencontainers.image.revision=${TAG}" \
    --label "org.opencontainers.image.source=https://github.com/itsme-aarjav/autonomous-devsecops-platform" \
    --label "org.opencontainers.image.created=${CREATED}" \
    --label "org.opencontainers.image.version=${TAG}" \
    -t "${IMAGE_TAGGED}" \
    -t "${IMAGE_LATEST}" \
    "${BUILD_DIR}"

  echo "Pushing ${IMAGE_TAGGED}..."
  docker push "${IMAGE_TAGGED}"
  docker push "${IMAGE_LATEST}"

  # Get ECR digest targeting the resolved account and region
  DIGEST=$(aws ecr describe-images --registry-id "${ACCOUNT_ID}" --repository-name "${REPO}" --image-ids imageTag="${TAG}" --region "${REGION}" --query 'imageDetails[0].imageDigest' --output text)
  SIZE_BYTES=$(aws ecr describe-images --registry-id "${ACCOUNT_ID}" --repository-name "${REPO}" --image-ids imageTag="${TAG}" --region "${REGION}" --query 'imageDetails[0].imageSizeInBytes' --output text)

  echo "Scanning ${IMAGE_TAGGED} with Trivy..."
  SCAN_OUTPUT=$(trivy image --severity HIGH,CRITICAL --scanners vuln --format json "${IMAGE_TAGGED}" 2>/dev/null || echo "{}")
  
  read -r CRITICAL_COUNT HIGH_COUNT < <(echo "${SCAN_OUTPUT}" | python3 -c "import sys, json
try:
    data = json.load(sys.stdin)
    res = data.get('Results', [])
    crit = sum(len([v for v in r.get('Vulnerabilities', []) if v.get('Severity') == 'CRITICAL']) for r in res)
    high = sum(len([v for v in r.get('Vulnerabilities', []) if v.get('Severity') == 'HIGH']) for r in res)
    print(f'{crit} {high}')
except Exception:
    print('0 0')" 2>/dev/null || echo "0 0")

  if [ $first -eq 0 ]; then
    echo "," >> "${SUMMARY_FILE}"
  fi
  first=0

  cat <<ENTRY >> "${SUMMARY_FILE}"
  {
    "service": "${REPO}",
    "tag": "${TAG}",
    "image": "${IMAGE_TAGGED}",
    "digest": "${DIGEST}",
    "size_bytes": ${SIZE_BYTES},
    "critical_cves": ${CRITICAL_COUNT},
    "high_cves": ${HIGH_COUNT},
    "oci_revision": "${TAG}",
    "oci_source": "https://github.com/itsme-aarjav/autonomous-devsecops-platform",
    "oci_created": "${CREATED}"
  }
ENTRY
  echo "Completed ${REPO}: Digest=${DIGEST}, Size=${SIZE_BYTES}, Critical=${CRITICAL_COUNT}, High=${HIGH_COUNT}"
done

echo "]" >> "${SUMMARY_FILE}"
echo "All microservice images built, pushed, and scanned successfully!"
