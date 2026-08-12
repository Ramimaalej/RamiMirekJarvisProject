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


# ── Clone & run (plain git — no API token needed for public repos) ───────

DEFAULT_CLONE_DIR = Path.home() / "MyProjects"


def clone_repo(repo: str, dest_dir: str | None = None, player=None) -> str:
    """Clone a GitHub repo into ~/MyProjects and return the local path.

    ``repo`` accepts a full URL (https://…, git@…:…) or ``owner/repo``.
    """
    import subprocess
    import shutil

    if not shutil.which("git"):
        return "git is not installed — install git first."

    repo = repo.strip().strip("'\"").rstrip("/")
    if not repo:
        return "Give me a repo, like 'clone https://github.com/user/repo' or 'user/repo'."

    # Normalise shorthand → https URL
    url = repo
    if repo.startswith(("git@", "ssh://")):
        # git@github.com:user/repo.git → user/repo
        name = repo.rstrip("/").split(":")[-1]
    else:
        name = Path(repo).name
    if not repo.startswith(("http://", "https://", "git@", "ssh://")):
        if "/" not in repo or repo.count("/") != 1:
            return f"'{repo}' does not look like a GitHub repo. Try 'owner/repo' or a full URL."
        url = f"https://github.com/{repo}.git"
        name = repo.split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]

    dest = (Path(dest_dir).expanduser() if dest_dir else DEFAULT_CLONE_DIR) / name
    if dest.exists():
        return f"Repo already exists at {dest}."

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest)],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip().splitlines()
            return f"Clone failed: {err[-1] if err else 'unknown error'}"
    except subprocess.TimeoutExpired:
        return "Clone timed out after 5 minutes."
    except Exception as e:
        return f"Clone failed: {e}"

    if player is not None:
        try:
            player.write_log(f"[github] cloned {name} → {dest}")
        except Exception:
            pass
    return str(dest)


def detect_run_command(folder: Path) -> str:
    """Figure out how to run a freshly cloned project. Returns a shell command."""
    if not folder.is_dir():
        return ""

    if (folder / "package.json").exists():
        scripts = ""
        try:
            import json as _json
            data = _json.loads((folder / "package.json").read_text(encoding="utf-8"))
            scripts = (data.get("scripts") or {}).get("dev") or (data.get("scripts") or {}).get("start", "")
        except Exception:
            scripts = ""
        if scripts:
            return "npm install && npm run dev"
        return "npm install && npm start"

    for f in ("requirements.txt", "pyproject.toml", "setup.py", "Pipfile"):
        if (folder / f).exists():
            for entry in ("main.py", "app.py", "run.py", "manage.py", "server.py", "wsgi.py"):
                if (folder / entry).exists():
                    return f"pip install -r requirements.txt && python {entry}"
            if (folder / "streamlit_app.py").exists():
                return "pip install -r requirements.txt && streamlit run streamlit_app.py"
            return "pip install -r requirements.txt && python main.py"

    if (folder / "docker-compose.yml").exists() or (folder / "docker-compose.yaml").exists():
        return "docker compose up"

    if (folder / "Makefile").exists():
        return "make run"

    if (folder / "go.mod").exists():
        return "go run ."

    if (folder / "Cargo.toml").exists():
        return "cargo run"

    return ""


def clone_and_run(repo: str, dest_dir: str | None = None, player=None) -> str:
    """Clone a repo, then open a terminal in it running the detected start command."""
    path_str = clone_repo(repo, dest_dir=dest_dir, player=player)
    # If the repo already exists, still open it — no need to re-clone.
    if path_str.startswith("Repo already exists"):
        existing = path_str.split(" at ", 1)[-1].rstrip(".")
        path_str = existing if Path(existing).is_dir() else path_str
    if path_str.startswith(("Clone failed", "git is not installed", "Give me", "'",
                            "Clone timed out")) or not Path(path_str).is_dir():
        return path_str

    folder = Path(path_str)
    try:
        from actions.fcc_runner import open_terminal_in
        run_cmd = detect_run_command(folder)
        command = run_cmd if run_cmd else "exec bash"
        if open_terminal_in(folder, command=command):
            if run_cmd:
                return f"Cloned {folder.name} to {folder} and started a terminal running '{run_cmd}'."
            return f"Cloned {folder.name} to {folder} and opened it in a terminal."
        return f"Cloned {folder.name} to {folder} (could not open a terminal)."
    except Exception as e:
        logger.warning("clone_and_run terminal open failed: %s", e)
        return f"Cloned {folder.name} to {folder}."

