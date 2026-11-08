"""
Autonomous AIOps Platform — Allowlisted Manifest Patch Renderer
"""

import re
import difflib
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Optional
import yaml

from .schemas import (
    RemediationProposal,
    RemediationActionType,
    PolicyDecision,
)
from .policy import WORKLOAD_MANIFEST_MAP, SECRET_PATTERNS
from .github_provider import BaseGitHubProvider, GitHubApiProvider


class ManifestRenderError(Exception):
    """Raised when manifest patch rendering fails or violates safety bounds."""
    pass


class RenderedPatch:
    """Encapsulates rendered manifest modifications and diffs."""

    def __init__(self, modified_files: Dict[str, str], diff: str, summary: str):
        self.modified_files = modified_files  # rel_path -> new_content
        self.diff = diff
        self.summary = summary


class ManifestPatchRenderer:
    """
    Renders declarative GitOps manifest modifications in memory.
    Enforces strict path containment, safe YAML mutation, and schema verification.
    """

    def __init__(self, repo_root: str, github_provider: Optional[BaseGitHubProvider] = None):
        self.repo_root = Path(repo_root).resolve()
        self.github_provider = github_provider

    def render_proposal_patch(self, proposal: RemediationProposal) -> RenderedPatch:
        """
        Renders the changes required by an approved proposal.
        Returns RenderedPatch containing modified file contents and unified diff.
        """
        if proposal.policy_decision != PolicyDecision.APPROVED:
            raise ManifestRenderError(
                f"Cannot render patch for unapproved proposal: status={proposal.policy_decision.value}"
            )

        # Determine target manifest file
        target_manifests = [proposal.target_manifest]

        modified_files: Dict[str, str] = {}
        all_diffs: List[str] = []

        for rel_manifest in target_manifests:
            # 1. Path containment check
            manifest_path = (self.repo_root / rel_manifest).resolve()
            if not manifest_path.is_relative_to(self.repo_root):
                raise ManifestRenderError(f"Security error: target manifest '{rel_manifest}' escapes repo root")

            # 2. Fetch fresh manifest content from GitHub if available, otherwise read from repo_root
            original_content = None
            if self.github_provider is not None:
                original_content = self.github_provider.get_file_content(rel_manifest)
                if original_content is None and isinstance(self.github_provider, GitHubApiProvider):
                    raise ManifestRenderError(
                        f"Target manifest '{rel_manifest}' could not be retrieved from live GitHub repository "
                        f"'{self.github_provider.repository}'. Fallback to stale container files rejected in live GitHub mode."
                    )

            if original_content is None:
                if manifest_path.is_file():
                    original_content = manifest_path.read_text(encoding="utf-8")
                else:
                    bundled_fallback = Path(__file__).parent / "manifests" / Path(rel_manifest).name
                    if bundled_fallback.is_file():
                        original_content = bundled_fallback.read_text(encoding="utf-8")
                    else:
                        raise ManifestRenderError(f"Target manifest file not found: {rel_manifest}")
            new_content = self._apply_remediation_to_yaml(
                original_content,
                proposal.workload,
                proposal.action_type,
                proposal.parameters,
            )

            # Generate unified diff
            diff_lines = list(difflib.unified_diff(
                original_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile=f"a/{rel_manifest}",
                tofile=f"b/{rel_manifest}",
            ))
            diff_str = "".join(diff_lines)

            # 2. Secret check on diff
            for pattern in SECRET_PATTERNS:
                if re.search(pattern, diff_str):
                    raise ManifestRenderError("Security error: Rendered diff contains potential secret pattern")

            modified_files[rel_manifest] = new_content
            if diff_str:
                all_diffs.append(diff_str)

        combined_diff = "\n".join(all_diffs)
        summary = self._generate_summary(proposal)

        return RenderedPatch(
            modified_files=modified_files,
            diff=combined_diff,
            summary=summary,
        )

    def _apply_remediation_to_yaml(
        self,
        yaml_content: str,
        workload: str,
        action_type: RemediationActionType,
        params,
    ) -> str:
        """
        Parses multi-document YAML, locates the target Deployment/Rollout,
        applies the change surgically, and outputs valid YAML.
        """
        try:
            docs = list(yaml.safe_load_all(yaml_content))
            original_docs = deepcopy(docs)
        except Exception as e:
            raise ManifestRenderError(f"Failed to parse manifest YAML: {str(e)}")

        matched = False
        updated_docs = []

        for doc in docs:
            if not isinstance(doc, dict):
                updated_docs.append(doc)
                continue

            kind = doc.get("kind", "")
            meta = doc.get("metadata", {})
            name = meta.get("name", "")

            # Target only the workload's Deployment or Rollout (supporting canonical and boutique- prefixed names)
            workload_names = {workload, f"boutique-{workload}", workload.removeprefix("boutique-")}
            if kind in ("Deployment", "Rollout") and name in workload_names:
                matched = True
                spec = doc.setdefault("spec", {})

                if action_type == RemediationActionType.SCALE_REPLICAS:
                    spec["replicas"] = params.replicas

                elif action_type in (RemediationActionType.SET_MEMORY_RESOURCES, RemediationActionType.SET_CPU_RESOURCES):
                    tmpl_spec = spec.setdefault("template", {}).setdefault("spec", {})
                    containers = tmpl_spec.setdefault("containers", [])
                    if not containers:
                        raise ManifestRenderError(f"No containers found in spec for workload {workload}")

                    # Find target container (or default to first container)
                    target_container = None
                    candidate_container_names = {
                        workload,
                        workload.removeprefix("boutique-"),
                    }
                    if params.target_container:
                        candidate_container_names.add(params.target_container)
                        candidate_container_names.add(params.target_container.removeprefix("boutique-"))

                    for c in containers:
                        if c.get("name") in candidate_container_names:
                            target_container = c
                            break
                    if not target_container:
                        target_container = containers[0]

                    res = target_container.setdefault("resources", {})
                    requests = res.setdefault("requests", {})
                    limits = res.setdefault("limits", {})

                    if action_type == RemediationActionType.SET_MEMORY_RESOURCES:
                        if params.memory_request:
                            requests["memory"] = params.memory_request
                        if params.memory_limit:
                            limits["memory"] = params.memory_limit

                    elif action_type == RemediationActionType.SET_CPU_RESOURCES:
                        if params.cpu_request:
                            requests["cpu"] = params.cpu_request
                        if params.cpu_limit:
                            limits["cpu"] = params.cpu_limit

                elif action_type == RemediationActionType.REVERT_IMAGE_DIGEST:
                    tmpl_spec = spec.setdefault("template", {}).setdefault("spec", {})
                    containers = tmpl_spec.setdefault("containers", [])
                    if not containers:
                        raise ManifestRenderError(f"No containers found for {workload}")
                    target_container = containers[0]
                    curr_image = target_container.get("image", "")
                    base_repo = curr_image.split("@")[0] if "@" in curr_image else curr_image.split(":")[0]
                    target_container["image"] = f"{base_repo}@{params.image_digest}"

            updated_docs.append(doc)

        if not matched:
            raise ManifestRenderError(f"Workload {workload} Deployment/Rollout not found in manifest")

        nodes = list(yaml.compose_all(yaml_content))
        if len(nodes) != len(updated_docs):
            raise ManifestRenderError("YAML document count changed")

        changes = []

        def visit(before, after, node):
            if before == after:
                return
            if isinstance(node, yaml.nodes.MappingNode) and isinstance(before, dict) and isinstance(after, dict):
                if before.keys() != after.keys():
                    raise ManifestRenderError("Unsupported YAML field change")
                for key_node, value_node in node.value:
                    key = key_node.value
                    if key not in before:
                        raise ManifestRenderError("Unsupported YAML mapping")
                    visit(before[key], after[key], value_node)
                return
            if isinstance(node, yaml.nodes.SequenceNode) and isinstance(before, list) and isinstance(after, list):
                if len(before) != len(after):
                    raise ManifestRenderError("Unsupported YAML list change")
                for old, new, value_node in zip(before, after, node.value):
                    visit(old, new, value_node)
                return
            if isinstance(node, yaml.nodes.ScalarNode) and isinstance(after, (str, int, float)) and not isinstance(after, bool):
                value = str(after)
                if not re.fullmatch(r"[A-Za-z0-9_./:@+-]+", value):
                    raise ManifestRenderError("Unsafe YAML scalar")
                changes.append((node.start_mark.index, node.end_mark.index, value))
                return
            raise ManifestRenderError("Unsupported YAML mutation")

        for before, after, node in zip(original_docs, updated_docs, nodes):
            visit(before, after, node)

        result = yaml_content
        for start, end, value in sorted(changes, reverse=True):
            result = result[:start] + value + result[end:]

        if list(yaml.safe_load_all(result)) != updated_docs:
            raise ManifestRenderError("YAML patch validation failed")
        return result

    def _generate_summary(self, proposal: RemediationProposal) -> str:
        """Constructs a concise human-readable summary of the rendered changes."""
        params = proposal.parameters
        if proposal.action_type == RemediationActionType.SCALE_REPLICAS:
            return f"Scale replicas to {params.replicas} for {proposal.workload}"
        elif proposal.action_type == RemediationActionType.SET_MEMORY_RESOURCES:
            parts = []
            if params.memory_request:
                parts.append(f"request={params.memory_request}")
            if params.memory_limit:
                parts.append(f"limit={params.memory_limit}")
            return f"Adjust memory resources ({', '.join(parts)}) for {proposal.workload}"
        elif proposal.action_type == RemediationActionType.SET_CPU_RESOURCES:
            parts = []
            if params.cpu_request:
                parts.append(f"request={params.cpu_request}")
            if params.cpu_limit:
                parts.append(f"limit={params.cpu_limit}")
            return f"Adjust CPU resources ({', '.join(parts)}) for {proposal.workload}"
        elif proposal.action_type == RemediationActionType.REVERT_IMAGE_DIGEST:
            return f"Revert image to {params.image_digest[:19]}... for {proposal.workload}"
        return f"Apply {proposal.action_type.value} for {proposal.workload}"

