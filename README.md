# herd-repo-github

Implements `RepoAdapter` from herd-core for GitHub.

Branch creation, pushes, pull requests, merges, and code review operations
via GitHub CLI and API.

Part of [The Herd](https://github.com/herd-ag/herd-core) ecosystem.

## Installation

```bash
pip install herd-repo-github
```

## Usage

```python
from herd_repo_github import GitHubRepoAdapter

adapter = GitHubRepoAdapter(repo_root="/path/to/repo")

# Create a branch
adapter.create_branch("herd/grunt/dbc-123-feature")

# Create a worktree
adapter.create_worktree("herd/grunt/dbc-123-feature", "/tmp/worktree")

# Push changes
adapter.push("herd/grunt/dbc-123-feature")

# Create a PR
pr_id = adapter.create_pr(
    title="Add feature",
    body="Description",
    head="herd/grunt/dbc-123-feature",
    base="main"
)
```

## License

MIT
