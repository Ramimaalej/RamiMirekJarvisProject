import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("github_integration")


class GitHubClient:
    def __init__(self, token: str | None = None):
        self._token = token or os.environ.get("GITHUB_TOKEN") or ""
        self._gh = None

    def _get_client(self):
        if self._gh is not None:
            return self._gh
        try:
            from github import Github
        except ImportError:
            raise ImportError("PyGithub not installed — pip install PyGithub")

        if not self._token:
            raise ValueError("GitHub token required — set GITHUB_TOKEN env or pass token= arg")
        self._gh = Github(self._token)
        return self._gh

    # ── Repos ──────────────────────────────────────────────────────────
    def list_repos(self, user: str | None = None) -> list[dict[str, Any]]:
        gh = self._get_client()
        if user:
            repos = gh.get_user(user).get_repos()
        else:
            repos = gh.get_user().get_repos()
        return [
            {
                "name": r.name,
                "full_name": r.full_name,
                "description": r.description or "",
                "url": r.html_url,
                "stars": r.stargazers_count,
                "forks": r.forks_count,
                "language": r.language or "",
                "private": r.private,
                "updated": str(r.updated_at),
            }
            for r in repos
        ]

    def create_repo(self, name: str, description: str = "", private: bool = False) -> dict:
        gh = self._get_client()
        repo = gh.get_user().create_repo(
            name=name,
            description=description,
            private=private,
            auto_init=True,
        )
        return {"name": repo.name, "url": repo.html_url, "clone_url": repo.clone_url}

    def get_repo(self, full_name: str) -> dict[str, Any] | None:
        gh = self._get_client()
        try:
            r = gh.get_repo(full_name)
            return {
                "name": r.name,
                "full_name": r.full_name,
                "description": r.description or "",
                "url": r.html_url,
                "stars": r.stargazers_count,
                "language": r.language or "",
                "default_branch": r.default_branch,
            }
        except Exception as e:
            logger.warning("get_repo error: %s", e)
            return None

    # ── Issues ─────────────────────────────────────────────────────────
    def list_issues(self, repo_full_name: str, state: str = "open") -> list[dict[str, Any]]:
        gh = self._get_client()
        repo = gh.get_repo(repo_full_name)
        return [
            {
                "number": i.number,
                "title": i.title,
                "state": i.state,
                "url": i.html_url,
                "labels": [l.name for l in i.labels],
                "created": str(i.created_at),
                "comments": i.comments,
            }
            for i in repo.get_issues(state=state)
        ]

    def create_issue(self, repo_full_name: str, title: str, body: str = "") -> dict:
        gh = self._get_client()
        repo = gh.get_repo(repo_full_name)
        issue = repo.create_issue(title=title, body=body)
        return {"number": issue.number, "url": issue.html_url, "state": issue.state}

    def close_issue(self, repo_full_name: str, issue_number: int) -> dict:
        gh = self._get_client()
        repo = gh.get_repo(repo_full_name)
        issue = repo.get_issue(number=issue_number)
        issue.edit(state="closed")
        return {"number": issue.number, "state": issue.state}

    # ── Pull Requests ──────────────────────────────────────────────────
    def list_prs(self, repo_full_name: str, state: str = "open") -> list[dict[str, Any]]:
        gh = self._get_client()
        repo = gh.get_repo(repo_full_name)
        return [
            {
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "url": pr.html_url,
                "author": pr.user.login if pr.user else "",
                "created": str(pr.created_at),
                "mergeable": pr.mergeable,
            }
            for pr in repo.get_pulls(state=state)
        ]

    def get_pr(self, repo_full_name: str, pr_number: int) -> dict[str, Any]:
        gh = self._get_client()
        repo = gh.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        return {
            "number": pr.number,
            "title": pr.title,
            "body": pr.body or "",
            "state": pr.state,
            "url": pr.html_url,
            "author": pr.user.login if pr.user else "",
            "base_branch": pr.base.ref,
            "head_branch": pr.head.ref,
            "mergeable": pr.mergeable,
            "merged": pr.merged,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "changed_files": pr.changed_files,
        }

    def create_pr(self, repo_full_name: str, title: str, head: str,
                  base: str = "main", body: str = "") -> dict:
        gh = self._get_client()
        repo = gh.get_repo(repo_full_name)
        pr = repo.create_pull(title=title, body=body, head=head, base=base)
        return {"number": pr.number, "url": pr.html_url, "state": pr.state}

    def merge_pr(self, repo_full_name: str, pr_number: int, commit_message: str = "") -> dict:
        gh = self._get_client()
        repo = gh.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        result = pr.merge(commit_message=commit_message or f"Merge PR #{pr_number}")
        return {"merged": result.merged, "sha": result.sha, "message": result.message}

    # ── Monitoring ─────────────────────────────────────────────────────
    def list_workflows(self, repo_full_name: str) -> list[dict[str, Any]]:
        gh = self._get_client()
        repo = gh.get_repo(repo_full_name)
        try:
            workflows = repo.get_workflows()
            return [
                {
                    "name": w.name,
                    "path": w.path,
                    "state": w.state,
                    "url": w.html_url,
                }
                for w in workflows
            ]
        except Exception as e:
            logger.warning("workflows error: %s", e)
            return []

    def list_workflow_runs(self, repo_full_name: str, branch: str = "") -> list[dict[str, Any]]:
        gh = self._get_client()
        repo = gh.get_repo(repo_full_name)
        runs = repo.get_workflow_runs(branch=branch if branch else None)
        return [
            {
                "id": r.id,
                "name": r.name,
                "status": r.status,
                "conclusion": r.conclusion,
                "branch": r.head_branch,
                "url": r.html_url,
                "created": str(r.created_at),
            }
            for r in runs
        ]


# ── Convenience ──────────────────────────────────────────────────────────

_client_cache: GitHubClient | None = None


def _get_client(token: str | None = None) -> GitHubClient:
    global _client_cache
    if _client_cache is None:
        _client_cache = GitHubClient(token=token)
    return _client_cache
