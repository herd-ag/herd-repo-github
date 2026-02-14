"""GitHub repository adapter implementation."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from herd_core.types import CommitInfo, PRRecord


class GitHubRepoAdapter:
    """GitHub implementation of the RepoAdapter protocol.

    Uses git CLI for repository operations and gh CLI for pull requests.
    """

    def __init__(
        self,
        repo_root: str,
        owner: str = "",
        name: str = "",
    ) -> None:
        """Initialize the GitHub repository adapter.

        Args:
            repo_root: Path to repository root.
            owner: Repository owner (e.g., "dbt-conceptual"). Auto-detected if not provided.
            name: Repository name (e.g., "dbt-conceptual"). Auto-detected if not provided.
        """
        self.repo_root = Path(repo_root)
        self.owner = owner
        self.name = name

        # Auto-detect owner/name from git remote if not provided
        if not owner or not name:
            self._detect_repo_info()

    def _detect_repo_info(self) -> None:
        """Auto-detect repository owner and name from git remote."""
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                check=True,
            )
            remote_url = result.stdout.strip()

            # Parse URLs like:
            # - https://github.com/owner/repo.git
            # - git@github.com:owner/repo.git
            if "github.com" in remote_url:
                if remote_url.startswith("git@"):
                    # git@github.com:owner/repo.git
                    parts = remote_url.split(":")[-1].replace(".git", "").split("/")
                else:
                    # https://github.com/owner/repo.git
                    parts = remote_url.replace(".git", "").split("/")[-2:]

                if len(parts) == 2:
                    self.owner = parts[0]
                    self.name = parts[1]
        except subprocess.CalledProcessError:
            pass

    def create_branch(self, name: str, *, base: str = "main") -> str:
        """Create a new branch from base.

        Args:
            name: Branch name.
            base: Base branch to create from.

        Returns:
            Created branch name.

        Raises:
            RuntimeError: If branch creation fails.
        """
        try:
            subprocess.run(
                ["git", "branch", name, base],
                cwd=str(self.repo_root),
                check=True,
                capture_output=True,
                text=True,
            )
            return name
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create branch {name}: {e.stderr}") from e

    def create_worktree(self, branch: str, path: str) -> str:
        """Create a git worktree for isolated agent work.

        Args:
            branch: Branch name (created if it doesn't exist).
            path: Filesystem path for the worktree.

        Returns:
            Absolute path to the created worktree.

        Raises:
            RuntimeError: If worktree creation fails.
        """
        worktree_path = Path(path).resolve()

        try:
            # Check if branch exists
            branch_check = subprocess.run(
                ["git", "rev-parse", "--verify", branch],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
            )

            if branch_check.returncode == 0:
                # Branch exists, create worktree from it
                subprocess.run(
                    ["git", "worktree", "add", str(worktree_path), branch],
                    cwd=str(self.repo_root),
                    check=True,
                    capture_output=True,
                    text=True,
                )
            else:
                # Branch doesn't exist, create it with worktree
                subprocess.run(
                    ["git", "worktree", "add", str(worktree_path), "-b", branch],
                    cwd=str(self.repo_root),
                    check=True,
                    capture_output=True,
                    text=True,
                )

            return str(worktree_path)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to create worktree at {worktree_path}: {e.stderr}"
            ) from e

    def remove_worktree(self, path: str) -> None:
        """Remove a git worktree after agent completion.

        Args:
            path: Path to the worktree to remove.

        Raises:
            RuntimeError: If worktree removal fails.
        """
        try:
            subprocess.run(
                ["git", "worktree", "remove", path],
                cwd=str(self.repo_root),
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to remove worktree at {path}: {e.stderr}") from e

    def push(self, branch: str) -> None:
        """Push a branch to the remote.

        Args:
            branch: Branch name to push.

        Raises:
            RuntimeError: If push fails.
        """
        try:
            subprocess.run(
                ["git", "push", "-u", "origin", branch],
                cwd=str(self.repo_root),
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to push branch {branch}: {e.stderr}") from e

    def create_pr(
        self,
        title: str,
        body: str,
        *,
        head: str,
        base: str = "main",
    ) -> str:
        """Create a pull request.

        Args:
            title: PR title.
            body: PR body/description.
            head: Head branch (source).
            base: Base branch (target).

        Returns:
            PR identifier (e.g., "123").

        Raises:
            RuntimeError: If PR creation fails.
        """
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--title",
                    title,
                    "--body",
                    body,
                    "--head",
                    head,
                    "--base",
                    base,
                    "--repo",
                    f"{self.owner}/{self.name}",
                ],
                cwd=str(self.repo_root),
                check=True,
                capture_output=True,
                text=True,
            )

            # Extract PR number from URL in output
            # Output is typically: https://github.com/owner/repo/pull/123
            pr_url = result.stdout.strip()
            pr_number = pr_url.split("/")[-1]
            return pr_number
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to create PR: {e.stderr}") from e

    def get_pr(self, pr_id: str) -> PRRecord:
        """Get current state of a pull request.

        Args:
            pr_id: PR identifier (number).

        Returns:
            PRRecord with PR details.

        Raises:
            RuntimeError: If fetching PR fails.
        """
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "view",
                    pr_id,
                    "--repo",
                    f"{self.owner}/{self.name}",
                    "--json",
                    "number,title,body,state,headRefName,baseRefName,url,additions,deletions,changedFiles,mergedAt,closedAt",
                ],
                cwd=str(self.repo_root),
                check=True,
                capture_output=True,
                text=True,
            )

            data = json.loads(result.stdout)

            # Parse timestamps
            merged_at = None
            if data.get("mergedAt"):
                merged_at = datetime.fromisoformat(
                    data["mergedAt"].replace("Z", "+00:00")
                )

            closed_at = None
            if data.get("closedAt"):
                closed_at = datetime.fromisoformat(
                    data["closedAt"].replace("Z", "+00:00")
                )

            return PRRecord(
                id=str(data["number"]),
                title=data.get("title", ""),
                branch=data.get("headRefName", ""),
                base=data.get("baseRefName", "main"),
                status=data.get("state", "").lower(),
                lines_added=data.get("additions", 0),
                lines_deleted=data.get("deletions", 0),
                files_changed=data.get("changedFiles", 0),
                url=data.get("url"),
                merged_at=merged_at,
                closed_at=closed_at,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to get PR {pr_id}: {e.stderr}") from e
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(f"Failed to parse PR data: {e}") from e

    def merge_pr(self, pr_id: str) -> None:
        """Merge a pull request.

        Args:
            pr_id: PR identifier (number).

        Raises:
            RuntimeError: If merge fails.
        """
        try:
            subprocess.run(
                [
                    "gh",
                    "pr",
                    "merge",
                    pr_id,
                    "--repo",
                    f"{self.owner}/{self.name}",
                    "--merge",  # Use merge commit (not squash or rebase)
                ],
                cwd=str(self.repo_root),
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to merge PR {pr_id}: {e.stderr}") from e

    def add_pr_comment(self, pr_id: str, body: str) -> None:
        """Add a review comment to a pull request.

        Args:
            pr_id: PR identifier (number).
            body: Comment body.

        Raises:
            RuntimeError: If adding comment fails.
        """
        try:
            subprocess.run(
                [
                    "gh",
                    "api",
                    f"repos/{self.owner}/{self.name}/issues/{pr_id}/comments",
                    "-f",
                    f"body={body}",
                ],
                cwd=str(self.repo_root),
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to add comment to PR {pr_id}: {e.stderr}"
            ) from e

    def get_log(
        self,
        *,
        since: datetime | None = None,
        branch: str | None = None,
        limit: int = 50,
    ) -> list[CommitInfo]:
        """Get commit log.

        Args:
            since: Only commits after this timestamp.
            branch: Branch to read log from. Defaults to current branch.
            limit: Maximum number of commits to return.

        Returns:
            List of commits, most recent first.

        Raises:
            RuntimeError: If reading log fails.
        """
        try:
            args = ["git", "log"]

            # Add since filter
            if since:
                args.append(f"--since={since.isoformat()}")

            # Add branch filter
            if branch:
                args.append(branch)

            # Limit results
            args.append(f"-{limit}")

            # Format: %H (hash), %an (author), %ai (ISO date), %s (subject)
            args.append("--format=%H|||%an|||%ai|||%s")

            result = subprocess.run(
                args,
                cwd=str(self.repo_root),
                check=True,
                capture_output=True,
                text=True,
            )

            commits = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("|||")
                if len(parts) != 4:
                    continue

                sha, author, timestamp_str, message = parts

                # Parse timestamp
                timestamp = datetime.fromisoformat(timestamp_str.replace(" ", "T"))

                commits.append(
                    CommitInfo(
                        sha=sha,
                        message=message,
                        author=author,
                        timestamp=timestamp,
                        branch=branch,
                    )
                )

            return commits
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to get git log: {e.stderr}") from e
