"""
Autonomous AIOps Platform — GitHub Provider Interface & Production Client
"""

import json
import logging
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = logging.getLogger("aiops.remediation.github")


class GitHubProviderError(Exception):
    """Base exception for GitHub API provider operations."""
    pass


class GitHubAuthError(GitHubProviderError):
    """Raised on authentication or permission failure (401/403)."""
    pass


class GitHubRateLimitError(GitHubProviderError):
    """Raised when GitHub API rate limit is exceeded (429)."""
    pass


class GitHubConflictError(GitHubProviderError):
    """Raised on stale base SHA or git conflict (409)."""
    pass


class BaseGitHubProvider(ABC):
    """Abstract provider interface for GitHub repository operations."""

    @abstractmethod
    def get_default_branch(self) -> str:
        """Returns default branch name (e.g. 'main')."""
        pass

    @abstractmethod
    def get_branch_head_sha(self, branch: str) -> str:
        """Returns the commit SHA at the HEAD of the given branch."""
        pass

    @abstractmethod
    def branch_exists(self, branch: str) -> bool:
        """Returns True if branch exists on remote."""
        pass

    @abstractmethod
    def commit_files(
        self,
        branch_name: str,
        files: Dict[str, str],
        commit_message: str,
        expected_parent_sha: Optional[str] = None,
    ) -> str:
        """Commits multiple modified files to the specified branch. Returns new commit SHA."""
        pass

    def create_branch(self, branch_name: str, base_sha: str) -> str:
        """Creates a new git branch from base_sha."""
        return base_sha

    def create_pull_request(
        self,
        title: str,
        head_branch: str,
        base_branch: str,
        body: str,
    ) -> Dict[str, Any]:
        """Creates a pull request."""
        return {"number": 1, "html_url": f"https://github.com/pulls/1"}

    def create_remediation_pr(
        self,
        proposal_id: str,
        files: Dict[str, str],
        commit_message: str,
        pr_title: str,
        pr_body: str,
    ) -> Dict[str, Any]:
        """
        Creates a dedicated remediation branch, commits changes to it,
        and opens a Pull Request against the default branch for human review.
        """
        default_branch = self.get_default_branch()
        base_sha = self.get_branch_head_sha(default_branch)
        branch_name = f"fix/aiops-proposal-{proposal_id[:8]}"

        if not self.branch_exists(branch_name):
            self.create_branch(branch_name, base_sha)

        commit_sha = self.commit_files(
            branch_name=branch_name,
            files=files,
            commit_message=commit_message,
            expected_parent_sha=base_sha,
        )

        pr_data = self.create_pull_request(
            title=pr_title,
            head_branch=branch_name,
            base_branch=default_branch,
            body=pr_body,
        )

        return {
            "pr_number": pr_data.get("number"),
            "pr_url": pr_data.get("html_url", ""),
            "branch": branch_name,
            "commit_sha": commit_sha,
        }

    def commit_to_main(
        self,
        files: Dict[str, str],
        commit_message: str,
        expected_parent_sha: Optional[str] = None,
    ) -> str:
        """Commits files directly to default branch ('main') without creating a separate branch."""
        default_branch = self.get_default_branch()
        return self.commit_files(
            branch_name=default_branch,
            files=files,
            commit_message=commit_message,
            expected_parent_sha=expected_parent_sha,
        )

    def get_file_content(self, path: str, ref: Optional[str] = None) -> Optional[str]:
        """Fetches raw text content of a file from GitHub repository at the specified ref. Returns None if unavailable."""
        return None

    def create_branch(self, branch_name: str, base_sha: str) -> str:
        """Creates a new git branch pointer at base_sha via GitHub Refs API."""
        resp = self._request("POST", f"/repos/{self.repository}/git/refs", {
            "ref": f"refs/heads/{branch_name}",
            "sha": base_sha,
        })
        return resp.get("object", {}).get("sha", base_sha)

    def create_pull_request(
        self,
        title: str,
        head_branch: str,
        base_branch: str,
        body: str,
    ) -> Dict[str, Any]:
        """Creates a Pull Request on GitHub for reviewed human merge."""
        return self._request("POST", f"/repos/{self.repository}/pulls", {
            "title": title,
            "head": head_branch,
            "base": base_branch,
            "body": body,
            "maintainer_can_modify": True,
        })

    def find_commit_for_proposal(
        self,
        proposal_id: str,
        branch: Optional[str] = None,
    ) -> Optional[str]:
        """
        Inspects remote branch commit history to find if a commit embedding
        'Proposal-ID: <proposal_id>' has already been applied.
        Returns commit SHA if found, or None.
        """
        return None


class GitHubApiProvider(BaseGitHubProvider):
    """
    Production GitHub REST API v3 provider using Python standard library urllib.
    Requires least-privilege token (contents:write, pull_requests:write).
    """

    def __init__(
        self,
        repository: str,
        token: Optional[str] = None,
        api_base_url: str = "https://api.github.com",
        timeout_seconds: float = 10.0,
    ):
        self.repository = repository
        self.token = token
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.api_base_url}{path}"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Autonomous-AIOps-Remediation-Agent",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        data_bytes = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                resp_bytes = resp.read()
                if not resp_bytes:
                    return {}
                return json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as e:
            code, body = e.code, e.read().decode("utf-8", errors="replace")
            if code in (401, 403):
                raise GitHubAuthError(f"GitHub authentication failure ({code}): {body}")
            if code == 429:
                raise GitHubRateLimitError(f"GitHub rate limit exceeded ({code}): {body}")
            if code == 409:
                raise GitHubConflictError(f"GitHub conflict/stale reference ({code}): {body}")
            if code == 404:
                return {}
            raise GitHubProviderError(f"GitHub API HTTP {code} on {method} {path}: {body}")
        except Exception as e:
            raise GitHubProviderError(f"GitHub connection error on {method} {path}: {str(e)}")

    def get_default_branch(self) -> str:
        return self._request("GET", f"/repos/{self.repository}").get("default_branch", "main")

    def get_branch_head_sha(self, branch: str) -> str:
        sha = self._request("GET", f"/repos/{self.repository}/git/ref/heads/{branch}").get("object", {}).get("sha")
        if not sha:
            raise GitHubProviderError(f"Failed to find HEAD SHA for branch '{branch}' in {self.repository}")
        return sha

    def branch_exists(self, branch: str) -> bool:
        return bool(self._request("GET", f"/repos/{self.repository}/git/ref/heads/{branch}").get("object", {}).get("sha"))

    def get_file_content(self, path: str, ref: Optional[str] = None) -> Optional[str]:
        """
        Fetches raw file content from GitHub repository at specified ref (or default branch).
        Returns decoded text content or None if not found (404).
        Propagates authentication, rate limit, and provider errors.
        """
        target_ref = ref or self.get_default_branch()
        clean_path = path.lstrip("/")
        try:
            import base64
            data = self._request("GET", f"/repos/{self.repository}/contents/{clean_path}?ref={target_ref}")
            if not data or not isinstance(data, dict) or "content" not in data:
                return None
            encoded = data["content"]
            return base64.b64decode(encoded).decode("utf-8")
        except (GitHubAuthError, GitHubRateLimitError, GitHubConflictError, GitHubProviderError):
            raise
        except Exception as e:
            logger.warning("Could not fetch file '%s' at ref '%s' from GitHub: %s", path, target_ref, str(e))
            raise GitHubProviderError(f"Failed to fetch '{path}' from GitHub: {str(e)}") from e

    def commit_files(
        self,
        branch_name: str,
        files: Dict[str, str],
        commit_message: str,
        expected_parent_sha: Optional[str] = None,
    ) -> str:
        """
        Creates a Git commit with modified files via the GitHub Git Data API.
        1. Creates blobs for modified files.
        2. Creates tree referencing new blobs with base_tree = parent_sha.
        3. Creates commit referencing tree and parent.
        4. Updates branch ref pointer.
        """
        parent_sha = expected_parent_sha or self.get_branch_head_sha(branch_name)

        tree_elements = []
        for path, content in files.items():
            blob = self._request("POST", f"/repos/{self.repository}/git/blobs", {"content": content, "encoding": "utf-8"})
            tree_elements.append({"path": path, "mode": "100644", "type": "blob", "sha": blob.get("sha")})

        tree = self._request("POST", f"/repos/{self.repository}/git/trees", {"base_tree": parent_sha, "tree": tree_elements})
        commit = self._request("POST", f"/repos/{self.repository}/git/commits", {"message": commit_message, "tree": tree.get("sha"), "parents": [parent_sha]})
        new_commit_sha = commit.get("sha")

        self._request("PATCH", f"/repos/{self.repository}/git/refs/heads/{branch_name}", {"sha": new_commit_sha, "force": False})
        return new_commit_sha

    def create_branch(self, branch_name: str, base_sha: str) -> str:
        """Creates a new git branch pointer at base_sha via GitHub Refs API."""
        resp = self._request("POST", f"/repos/{self.repository}/git/refs", {
            "ref": f"refs/heads/{branch_name}",
            "sha": base_sha,
        })
        return resp.get("object", {}).get("sha", base_sha)

    def create_pull_request(
        self,
        title: str,
        head_branch: str,
        base_branch: str,
        body: str,
    ) -> Dict[str, Any]:
        """Creates a Pull Request on GitHub for reviewed human merge."""
        return self._request("POST", f"/repos/{self.repository}/pulls", {
            "title": title,
            "head": head_branch,
            "base": base_branch,
            "body": body,
            "maintainer_can_modify": True,
        })

    def find_commit_for_proposal(
        self,
        proposal_id: str,
        branch: Optional[str] = None,
        max_pages: int = 10,
        per_page: int = 100,
    ) -> Optional[str]:
        """
        Inspects remote branch commit history across paginated batches to find if a commit
        embedding 'Proposal-ID: <proposal_id>' has already been applied.
        Fails closed by propagating GitHubProviderError / GitHubRateLimitError / GitHubAuthError.
        """
        target_branch = branch or self.get_default_branch()
        needle = f"Proposal-ID: {proposal_id}"

        for page in range(1, max_pages + 1):
            commits = self._request(
                "GET",
                f"/repos/{self.repository}/commits?sha={target_branch}&per_page={per_page}&page={page}",
            )
            if not commits or not isinstance(commits, list):
                break
            for c in commits:
                msg = c.get("commit", {}).get("message", "")
                if any(line.strip() == needle for line in msg.splitlines()):
                    return c.get("sha")
            if len(commits) < per_page:
                break

        return None

