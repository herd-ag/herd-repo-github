"""Tests for GitHubRepoAdapter."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from herd_core.adapters.repo import RepoAdapter
from herd_core.types import CommitInfo, PRRecord
from herd_repo_github import GitHubRepoAdapter


@pytest.fixture
def adapter():
    """Create a test adapter instance."""
    with patch("subprocess.run") as mock_run:
        # Mock the git remote get-url call in __init__
        mock_run.return_value = MagicMock(
            stdout="https://github.com/test-owner/test-repo.git\n",
            returncode=0,
        )
        adapter = GitHubRepoAdapter(repo_root="/tmp/test-repo")
        yield adapter


def test_isinstance_check(adapter):
    """Test that adapter implements RepoAdapter protocol."""
    assert isinstance(adapter, RepoAdapter)


def test_init_auto_detect_owner_name():
    """Test automatic detection of owner and name from git remote."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="https://github.com/dbt-conceptual/herd-repo-github.git\n",
            returncode=0,
        )

        adapter = GitHubRepoAdapter(repo_root="/tmp/test")

        assert adapter.owner == "dbt-conceptual"
        assert adapter.name == "herd-repo-github"


def test_init_ssh_remote():
    """Test detection with SSH remote URL."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="git@github.com:dbt-conceptual/herd-repo-github.git\n",
            returncode=0,
        )

        adapter = GitHubRepoAdapter(repo_root="/tmp/test")

        assert adapter.owner == "dbt-conceptual"
        assert adapter.name == "herd-repo-github"


def test_init_explicit_owner_name():
    """Test explicit owner and name override auto-detection."""
    with patch("subprocess.run"):
        adapter = GitHubRepoAdapter(
            repo_root="/tmp/test",
            owner="custom-owner",
            name="custom-repo",
        )

        assert adapter.owner == "custom-owner"
        assert adapter.name == "custom-repo"


def test_create_branch(adapter):
    """Test branch creation."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = adapter.create_branch("feature-branch", base="main")

        assert result == "feature-branch"
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[:3] == ["git", "branch", "feature-branch"]


def test_create_branch_failure(adapter):
    """Test branch creation failure."""
    import subprocess

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["git", "branch"],
            stderr="Branch creation failed",
        )

        with pytest.raises(RuntimeError, match="Failed to create branch"):
            adapter.create_branch("bad-branch")


def test_create_worktree_new_branch(adapter):
    """Test worktree creation with new branch."""
    with patch("subprocess.run") as mock_run:
        # First call: branch check (fails - branch doesn't exist)
        # Second call: worktree creation
        mock_run.side_effect = [
            MagicMock(returncode=1),  # Branch doesn't exist
            MagicMock(returncode=0),  # Worktree created
        ]

        result = adapter.create_worktree("new-branch", "/tmp/worktree")

        assert Path(result).is_absolute()
        assert "worktree" in result
        assert mock_run.call_count == 2


def test_create_worktree_existing_branch(adapter):
    """Test worktree creation with existing branch."""
    with patch("subprocess.run") as mock_run:
        # First call: branch check (succeeds)
        # Second call: worktree creation
        mock_run.side_effect = [
            MagicMock(returncode=0),  # Branch exists
            MagicMock(returncode=0),  # Worktree created
        ]

        result = adapter.create_worktree("existing-branch", "/tmp/worktree")

        assert Path(result).is_absolute()
        assert mock_run.call_count == 2


def test_remove_worktree(adapter):
    """Test worktree removal."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        adapter.remove_worktree("/tmp/worktree")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[:3] == ["git", "worktree", "remove"]


def test_push(adapter):
    """Test branch push."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        adapter.push("feature-branch")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["git", "push", "-u", "origin", "feature-branch"]


def test_create_pr(adapter):
    """Test PR creation."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="https://github.com/test-owner/test-repo/pull/42\n",
            returncode=0,
        )

        pr_id = adapter.create_pr(
            title="Test PR",
            body="Test description",
            head="feature-branch",
            base="main",
        )

        assert pr_id == "42"
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "gh" in args[0]
        assert "pr" in args[1]
        assert "create" in args[2]


def test_get_pr(adapter):
    """Test fetching PR details."""
    pr_data = {
        "number": 42,
        "title": "Test PR",
        "body": "Description",
        "state": "OPEN",
        "headRefName": "feature-branch",
        "baseRefName": "main",
        "url": "https://github.com/test-owner/test-repo/pull/42",
        "additions": 100,
        "deletions": 50,
        "changedFiles": 5,
        "mergedAt": None,
        "closedAt": None,
    }

    with patch("subprocess.run") as mock_run:
        import json

        mock_run.return_value = MagicMock(
            stdout=json.dumps(pr_data),
            returncode=0,
        )

        pr = adapter.get_pr("42")

        assert isinstance(pr, PRRecord)
        assert pr.id == "42"
        assert pr.title == "Test PR"
        assert pr.branch == "feature-branch"
        assert pr.base == "main"
        assert pr.status == "open"
        assert pr.lines_added == 100
        assert pr.lines_deleted == 50
        assert pr.files_changed == 5


def test_get_pr_with_timestamps(adapter):
    """Test fetching PR with merged/closed timestamps."""
    pr_data = {
        "number": 42,
        "title": "Test PR",
        "state": "MERGED",
        "headRefName": "feature-branch",
        "baseRefName": "main",
        "additions": 10,
        "deletions": 5,
        "changedFiles": 2,
        "mergedAt": "2024-02-14T12:00:00Z",
        "closedAt": "2024-02-14T12:00:00Z",
    }

    with patch("subprocess.run") as mock_run:
        import json

        mock_run.return_value = MagicMock(
            stdout=json.dumps(pr_data),
            returncode=0,
        )

        pr = adapter.get_pr("42")

        assert pr.merged_at is not None
        assert pr.closed_at is not None


def test_merge_pr(adapter):
    """Test PR merge."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        adapter.merge_pr("42")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "gh" in args[0]
        assert "pr" in args[1]
        assert "merge" in args[2]


def test_add_pr_comment(adapter):
    """Test adding PR comment."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        adapter.add_pr_comment("42", "Test comment")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "gh" in args[0]
        assert "api" in args[1]


def test_get_log(adapter):
    """Test getting commit log."""
    git_log_output = (
        "abc123|||John Doe|||2024-02-14 12:00:00 +0000|||First commit\n"
        "def456|||Jane Smith|||2024-02-14 11:00:00 +0000|||Second commit\n"
    )

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout=git_log_output,
            returncode=0,
        )

        commits = adapter.get_log(limit=10)

        assert len(commits) == 2
        assert isinstance(commits[0], CommitInfo)
        assert commits[0].sha == "abc123"
        assert commits[0].author == "John Doe"
        assert commits[0].message == "First commit"
        assert isinstance(commits[0].timestamp, datetime)


def test_get_log_with_filters(adapter):
    """Test getting commit log with filters."""
    since = datetime(2024, 2, 1)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="",
            returncode=0,
        )

        adapter.get_log(since=since, branch="feature-branch", limit=20)

        args = mock_run.call_args[0][0]
        assert "--since=" in " ".join(args)
        assert "feature-branch" in args
        assert "-20" in args


def test_get_log_parsing_error(adapter):
    """Test handling of malformed git log output."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            stdout="malformed|||output\n",
            returncode=0,
        )

        commits = adapter.get_log()

        # Should skip malformed lines
        assert len(commits) == 0


def test_error_handling_git_failure(adapter):
    """Test error handling for git command failures."""
    with patch("subprocess.run") as mock_run:
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["git", "push"],
            stderr="Permission denied",
        )

        with pytest.raises(RuntimeError, match="Failed to push branch"):
            adapter.push("feature-branch")


def test_error_handling_gh_failure(adapter):
    """Test error handling for gh command failures."""
    with patch("subprocess.run") as mock_run:
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["gh", "pr", "create"],
            stderr="Authentication failed",
        )

        with pytest.raises(RuntimeError, match="Failed to create PR"):
            adapter.create_pr(
                title="Test",
                body="Test",
                head="feature",
            )
