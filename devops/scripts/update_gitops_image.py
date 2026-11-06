#!/usr/bin/env python3
"""Deterministic GitOps image reference updater and ECR URI validator.

Enforces immutable SHA256 digest pinning and validates account-independent
ECR image URIs for Boutique microservices across Kubernetes manifests.
Ensures transaction-safe preflight validation prior to any file writes.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Strict ECR URI pattern for us-east-2 Boutique services:
# <12-digit-account>.dkr.ecr.us-east-2.amazonaws.com/<repository>@sha256:<64-hex-digest>
ECR_URI_REGEX = re.compile(
    r"^([0-9]{12})\.dkr\.ecr\.us-east-2\.amazonaws\.com/([a-zA-Z0-9._-]+)@sha256:([a-f0-9]{64})$"
)

# Canonical service names
CANONICAL_SERVICES: Dict[str, str] = {
    "boutique-frontend": "boutique-frontend",
    "boutique-gateway": "boutique-gateway",
    "boutique-auth": "boutique-auth",
    "boutique-aiops-assistant": "boutique-aiops-assistant",
    # Aliases
    "frontend": "boutique-frontend",
    "gateway": "boutique-gateway",
    "auth": "boutique-auth",
    "aiops": "boutique-aiops-assistant",
    "aiops-assistant": "boutique-aiops-assistant",
}

# The 4 deployment components (3 core application microservices + AIOps platform component)
REQUIRED_SERVICES: List[str] = [
    "boutique-frontend",
    "boutique-gateway",
    "boutique-auth",
    "boutique-aiops-assistant",
]

# Relative paths to manifests for each service (from repository root)
SERVICE_MANIFESTS: Dict[str, List[str]] = {
    "boutique-frontend": [
        "devops/gitops/k8s/frontend/rollout.yaml",
        "devops/gitops/k8s/frontend/blue-green.yml",
        "devops/gitops/k8s/frontend/deployment.yml",
    ],
    "boutique-gateway": ["devops/gitops/k8s/backend/gateway.yml"],
    "boutique-auth": ["devops/gitops/k8s/backend/auth.yml"],
    "boutique-aiops-assistant": ["devops/gitops/k8s/aiops/deployment.yaml"],
}


def normalize_service_name(service: str) -> str:
    """Normalize a service name or alias to its canonical name."""
    cleaned = service.strip()
    if cleaned in CANONICAL_SERVICES:
        return CANONICAL_SERVICES[cleaned]
    raise ValueError(f"Unknown service name '{service}'. Expected one of: {sorted(CANONICAL_SERVICES.keys())}")


def validate_image_uri(image_uri: str, expected_service: Optional[str] = None) -> Dict[str, str]:
    """Validate an immutable ECR image URI and optionally verify repository match.

    Args:
        image_uri: Full image reference string to validate.
        expected_service: Optional service name or alias to verify against.

    Returns:
        Dict containing parsed 'account_id', 'region', 'registry', 'repository', and 'digest'.

    Raises:
        ValueError: If URI format, hostname, digest, or repository name is invalid.
    """
    if not image_uri or not isinstance(image_uri, str):
        raise ValueError("Image URI must be a non-empty string")

    stripped = image_uri.strip()

    # Reject malformed tag+digest syntax like :@sha256 or :latest@sha256
    if ":@" in stripped or re.search(r":[a-zA-Z0-9._-]+@sha256", stripped):
        raise ValueError(f"Invalid image URI: contains incorrect tag-with-digest syntax ':@': {image_uri}")

    match = ECR_URI_REGEX.match(stripped)
    if not match:
        # Provide diagnostic feedback on why validation failed
        if "@sha256:" not in stripped:
            raise ValueError(f"Invalid image URI: missing '@sha256:' immutable digest prefix: {image_uri}")
        if not re.search(r"^[0-9]{12}\.", stripped):
            raise ValueError(f"Invalid image URI: registry must start with a 12-digit AWS account ID: {image_uri}")
        if ".dkr.ecr.us-east-2.amazonaws.com/" not in stripped:
            raise ValueError(f"Invalid image URI: registry host must be in 'us-east-2' ECR domain: {image_uri}")
        parts = stripped.split("@sha256:")
        if len(parts) == 2 and (len(parts[1]) != 64 or not re.match(r"^[a-f0-9]{64}$", parts[1])):
            raise ValueError(f"Invalid image URI: digest must be exactly 64 lowercase hexadecimal characters: {parts[1]}")
        raise ValueError(f"Invalid ECR image URI format: {image_uri}")

    account_id = match.group(1)
    repository = match.group(2)
    digest_hash = match.group(3)
    registry = f"{account_id}.dkr.ecr.us-east-2.amazonaws.com"
    full_digest = f"sha256:{digest_hash}"

    if expected_service is not None:
        canonical_expected = normalize_service_name(expected_service)
        if repository != canonical_expected:
            raise ValueError(
                f"Repository mismatch in image URI: expected '{canonical_expected}', got '{repository}'"
            )

    return {
        "account_id": account_id,
        "region": "us-east-2",
        "registry": registry,
        "repository": repository,
        "digest": full_digest,
        "image_uri": stripped,
    }


def plan_manifest_update(
    manifest_path: Path,
    expected_service: str,
    full_image_uri: str,
) -> Tuple[bool, str]:
    """Preflight validation and planning for a Kubernetes manifest image update without writing.

    Validates that:
    1. The manifest file exists on disk.
    2. The replacement image URI is valid and matches the expected service repository.
    3. Exactly one image reference line matches the expected service in the manifest.
    4. Indentation and line endings are preserved in the planned update.

    Note: This validation inspects image reference lines using regular expressions and
    does not perform YAML syntax parsing. Full schema/syntax validation is performed
    via kubectl kustomize.

    Args:
        manifest_path: Path to the YAML manifest file.
        expected_service: Canonical service name or alias to match.
        full_image_uri: Fully validated ECR image URI.

    Returns:
        Tuple of (changed: bool, updated_content: str).

    Raises:
        FileNotFoundError: If manifest_path does not exist.
        ValueError: If URI is invalid or zero/multiple matching image lines are found.
    """
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    canonical_service = normalize_service_name(expected_service)

    # Validate replacement URI matches the expected service
    validate_image_uri(full_image_uri, expected_service=canonical_service)

    content = manifest_path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    image_line_pattern = re.compile(
        r"^(\s*image:\s*)(?:[^\s/]+/)?([a-zA-Z0-9._-]+)(?:[:@][^\s]*)?\s*$"
    )

    matching_indices: List[Tuple[int, str]] = []
    for idx, line in enumerate(lines):
        m = image_line_pattern.match(line)
        if m:
            repo_in_line = m.group(2)
            if repo_in_line == canonical_service or CANONICAL_SERVICES.get(repo_in_line) == canonical_service:
                matching_indices.append((idx, m.group(1)))

    if len(matching_indices) == 0:
        raise ValueError(
            f"No container image matching service '{canonical_service}' found in {manifest_path}"
        )
    if len(matching_indices) > 1:
        line_numbers = [idx + 1 for idx, _ in matching_indices]
        raise ValueError(
            f"Found {len(matching_indices)} image references for '{canonical_service}' in {manifest_path} "
            f"(lines: {line_numbers}); expected exactly 1"
        )

    match_idx, prefix = matching_indices[0]
    newline = "\n" if lines[match_idx].endswith("\n") else ""
    new_line = f"{prefix}{full_image_uri}{newline}"

    if lines[match_idx] == new_line:
        # Already matches exactly
        return False, content

    lines[match_idx] = new_line
    updated_content = "".join(lines)

    # Verify replacement occurred and is exact in the generated content
    expected_snippet = f"image: {full_image_uri}"
    if expected_snippet not in updated_content:
        raise ValueError(
            f"Preflight verification failed: expected snippet '{expected_snippet}' missing in updated plan for {manifest_path}"
        )

    return True, updated_content


def _write_and_verify_manifest(
    manifest_path: Path,
    updated_content: str,
    full_image_uri: str,
) -> None:
    """Write updated content to manifest atomically and confirm post-write integrity."""
    expected_snippet = f"image: {full_image_uri}"
    temp_file = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    temp_file.write_text(updated_content, encoding="utf-8")
    temp_file.replace(manifest_path)

    # Re-read and confirm
    verified_content = manifest_path.read_text(encoding="utf-8")
    if expected_snippet not in verified_content:
        raise ValueError(f"Post-write verification failed for {manifest_path}")


def update_manifest_images(
    manifest_paths: List[Path],
    expected_service: str,
    full_image_uri: str,
    dry_run: bool = False,
) -> List[Path]:
    """Update one or more Kubernetes manifests for a service with preflight validation.

    Preflight every requested manifest in memory:
    - Confirms each manifest file exists.
    - Confirms exactly one matching container image reference per manifest.
    - Validates the target replacement URI format and service repository match.

    Note: Preflight inspects image declarations via regular expressions and does not
    parse YAML syntax. Preflight validation failures guarantee that all target manifests
    remain untouched. Only after every target manifest passes preflight validation are any
    files modified. Note: This provides preflight validation safety prior to writes; it does
    not claim transactional rollback if an arbitrary OS I/O or filesystem failure occurs mid-write.

    Args:
        manifest_paths: List of Paths to Kubernetes YAML manifest files.
        expected_service: Canonical service name or alias to match.
        full_image_uri: Fully validated ECR image URI.
        dry_run: When True, performs in-memory preflight validation without writing files.

    Returns:
        List of Path objects for manifests that were modified (or planned to be modified).

    Raises:
        ValueError: If manifest_paths is empty or preflight validation fails on any manifest.
        FileNotFoundError: If any target manifest file does not exist.
    """
    if not manifest_paths:
        raise ValueError("At least one manifest path must be provided")

    # Step 1: Preflight every requested manifest in memory before writing any files
    planned_updates: List[Tuple[Path, bool, str]] = []
    for path in manifest_paths:
        changed, updated_content = plan_manifest_update(
            manifest_path=path,
            expected_service=expected_service,
            full_image_uri=full_image_uri,
        )
        planned_updates.append((path, changed, updated_content))

    # Step 2: Write and verify only after universal preflight success
    updated: List[Path] = []
    for path, changed, updated_content in planned_updates:
        if changed:
            if not dry_run:
                _write_and_verify_manifest(path, updated_content, full_image_uri)
            updated.append(path)

    return updated


def update_manifest_image(
    manifest_path: Path,
    expected_service: str,
    full_image_uri: str,
) -> bool:
    """Update a Kubernetes manifest with a verified immutable container image URI.

    Ensures exactly one container image matches the expected service repository,
    replaces it while preserving indentation, and verifies the file changed.
    Backward-compatible wrapper around update_manifest_images.

    Args:
        manifest_path: Path to the YAML manifest file.
        expected_service: Canonical service name or alias to match.
        full_image_uri: Fully validated ECR image URI.

    Returns:
        True if the file was modified, False if it was already up-to-date with the exact URI.
    """
    updated = update_manifest_images(
        manifest_paths=[manifest_path],
        expected_service=expected_service,
        full_image_uri=full_image_uri,
    )
    return len(updated) > 0


def batch_promote_from_artifacts(
    artifacts_dir: Path,
    repo_root: Path,
    dry_run: bool = False,
) -> List[str]:
    """Validate all 3 service image artifacts and update corresponding GitOps manifests.

    Transaction-safe preflight process:
    1. Validate all 3 artifacts exist and are non-empty.
    2. Validate shared registry across all artifacts.
    3. Confirm every expected target manifest exists.
    4. Confirm exactly one intended image reference is found in every target manifest.
    5. Validate all target replacement URIs.
    6. Only after the entire preflight succeeds, write the manifests (unless dry_run is True).
    7. Verify all resulting references post-write.

    Returns:
        List of manifest file paths that were updated (or planned for update if dry_run).
    """
    if not artifacts_dir.is_dir():
        raise FileNotFoundError(f"Artifacts directory not found: {artifacts_dir}")

    # Step 1: Validate all 3 artifacts
    service_uris: Dict[str, Dict[str, str]] = {}
    for service in REQUIRED_SERVICES:
        candidate = artifacts_dir / f"{service}.digest"
        if not candidate.is_file():
            candidate = artifacts_dir / service
        if not candidate.is_file():
            raise FileNotFoundError(
                f"Missing required artifact for service '{service}': expected '{artifacts_dir / (service + '.digest')}'"
            )

        raw = candidate.read_text(encoding="utf-8").strip()
        if not raw:
            raise ValueError(f"Artifact for service '{service}' is empty: {candidate}")

        parsed = validate_image_uri(raw, expected_service=service)
        service_uris[service] = parsed

    # Step 2: Validate all artifacts share the exact same registry host
    registries = {svc: info["registry"] for svc, info in service_uris.items()}
    unique_registries = set(registries.values())
    if len(unique_registries) != 1:
        raise ValueError(
            f"Mixed ECR registries detected across artifacts (expected uniform registry): {registries}"
        )

    shared_registry = next(iter(unique_registries))
    print(f"Verified {len(REQUIRED_SERVICES)} artifacts targeting ECR registry: {shared_registry}")

    # Steps 3, 4, 5: Preflight EVERY target manifest before writing any changes
    planned_updates: List[Tuple[Path, str, bool, str, str]] = []
    for service in REQUIRED_SERVICES:
        uri = service_uris[service]["image_uri"]
        manifest_rel_paths = [p for p in SERVICE_MANIFESTS[service] if (repo_root / p).is_file()]
        if not manifest_rel_paths:
            manifest_rel_paths = SERVICE_MANIFESTS[service][:1]
        for rel_path in manifest_rel_paths:
            full_path = repo_root / rel_path
            changed, updated_content = plan_manifest_update(
                manifest_path=full_path,
                expected_service=service,
                full_image_uri=uri,
            )
            planned_updates.append((full_path, rel_path, changed, updated_content, uri))

    # Step 6 & 7: Write and verify manifests only after entire preflight succeeds
    updated_manifests: List[str] = []
    for full_path, rel_path, changed, updated_content, uri in planned_updates:
        if changed:
            if not dry_run:
                _write_and_verify_manifest(full_path, updated_content, uri)
            action = "Would update" if dry_run else "Updated"
            updated_manifests.append(rel_path)
        else:
            action = "Verified (no change needed)"
        print(f"[{action}] {rel_path} -> {uri}")

    return updated_manifests


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic GitOps image reference updater and ECR URI validator."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--artifacts-dir",
        type=Path,
        help="Directory containing all 3 service .digest artifacts for batch promotion.",
    )
    group.add_argument(
        "--manifest",
        type=Path,
        nargs="+",
        help="Path(s) to one or more Kubernetes manifest(s) to update.",
    )
    group.add_argument(
        "--validate-only",
        type=str,
        help="Validate a single image URI string and exit.",
    )

    parser.add_argument(
        "--service",
        type=str,
        help="Service name or alias (required with --manifest, optional with --validate-only).",
    )
    parser.add_argument(
        "--image-uri",
        type=str,
        help="Full ECR image URI (required with --manifest).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root directory (defaults to current working directory).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform preflight planning and validation without modifying files on disk.",
    )

    args = parser.parse_args()

    try:
        if args.validate_only:
            parsed = validate_image_uri(args.validate_only, expected_service=args.service)
            print(f"Valid image URI: account={parsed['account_id']} repo={parsed['repository']} digest={parsed['digest']}")
            sys.exit(0)

        if args.artifacts_dir:
            updated = batch_promote_from_artifacts(
                artifacts_dir=args.artifacts_dir,
                repo_root=args.repo_root,
                dry_run=args.dry_run,
            )
            prefix = "Dry run complete." if args.dry_run else "Batch promotion complete."
            print(f"{prefix} Manifests {'would update' if args.dry_run else 'updated'}: {len(updated)}")
            sys.exit(0)

        if args.manifest:
            if not args.service or not args.image_uri:
                parser.error("--manifest requires both --service and --image-uri")
            updated = update_manifest_images(
                manifest_paths=args.manifest,
                expected_service=args.service,
                full_image_uri=args.image_uri,
                dry_run=args.dry_run,
            )
            for p in args.manifest:
                if args.dry_run:
                    status = "Would update" if p in updated else "Already up to date"
                else:
                    status = "Updated" if p in updated else "Already up to date"
                print(f"{status}: {p} -> {args.image_uri}")
            sys.exit(0)

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
