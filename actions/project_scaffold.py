import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("project_scaffold")

WORKSPACE_DIR = Path(__file__).resolve().parent.parent / "workspace"

ROLES = [
    {
        "name": "project_manager",
        "label": "Project Manager",
        "system_prompt": "You are a senior Project Manager. Gather requirements, plan architecture, define milestones. Ask targeted questions until the spec is clear. Output a concise PRD.",
    },
    {
        "name": "backend",
        "label": "Backend Developer",
        "system_prompt": "You are a senior Backend Engineer. Build robust APIs, data models, business logic. Follow best practices. Output complete, runnable code.",
    },
    {
        "name": "frontend",
        "label": "Frontend Developer",
        "system_prompt": "You are a senior Frontend Engineer. Build clean, responsive UIs. Match the backend API. Output complete, runnable code.",
    },
    {
        "name": "tester",
        "label": "QA Engineer",
        "system_prompt": "You are a senior QA Engineer. Write comprehensive tests. Validate requirements. Output test suites with good coverage.",
    },
]


def _project_slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\-]", "-", name.lower()).strip("-")
    return slug or "new-project"


def _open_editor(project_dir: Path) -> bool:
    candidates = ["code", "vim", "nano"]
    for cmd in candidates:
        try:
            subprocess.Popen([cmd, str(project_dir)], shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            continue
    return False


def _run_opencode(project_dir: Path, role: dict, speak: Callable | None = None) -> str:
    opencode_cmd = "opencode"
    try:
        subprocess.run([opencode_cmd, "--version"], capture_output=True, timeout=5)
    except Exception:
        return f"opencode CLI not found — cannot start {role['label']} session."

    role_dir = project_dir / role["name"]
    role_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = role_dir / ".opencode-prompt"
    prompt_file.write_text(
        f"""Role: {role['label']}

{role['system_prompt']}

Project is in: {project_dir}
Your work goes in: {role_dir}

Start by understanding the project context, then deliver your artifacts.
"""
    )

    msg = f"Starting {role['label']} session in {role_dir}..."
    if speak:
        speak(msg)

    proc = subprocess.Popen(
        [opencode_cmd, str(role_dir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(role_dir),
    )

    threading.Thread(target=proc.wait, daemon=True).start()
    return f"{role['label']} session started (PID: {proc.pid})."


def start_project(
    project_name: str,
    description: str = "",
    tech_stack: str = "",
    workspace: str = "",
    roles: list[str] | None = None,
    speak: Callable | None = None,
) -> str:
    ws = Path(workspace) if workspace else WORKSPACE_DIR
    ws.mkdir(parents=True, exist_ok=True)

    slug = _project_slug(project_name)
    project_dir = ws / slug
    project_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "project_name": project_name,
        "slug": slug,
        "description": description,
        "tech_stack": tech_stack,
        "created": __import__("datetime").datetime.now().isoformat(),
        "phases": [],
    }
    manifest_path = project_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    readme = project_dir / "README.md"
    readme.write_text(
        f"# {project_name}\n\n{description}\n\n## Tech Stack\n{tech_stack}\n\n## Phases\n- [ ] Project Management\n- [ ] Backend Development\n- [ ] Frontend Development\n- [ ] Testing\n"
    )

    active_roles = [r for r in ROLES if r["name"] in (roles or ["project_manager", "backend", "frontend", "tester"])]

    results = [f"Project '{project_name}' scaffolded at {project_dir}"]
    for r in active_roles:
        result = _run_opencode(project_dir, r, speak)
        results.append(result)
        time.sleep(1)

    _open_editor(project_dir)
    return "\n".join(results)


def list_projects(workspace: str = "") -> list[dict[str, Any]]:
    ws = Path(workspace) if workspace else WORKSPACE_DIR
    if not ws.exists():
        return []
    projects = []
    for d in ws.iterdir():
        if d.is_dir():
            manifest_path = d / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    projects.append(manifest)
                except Exception:
                    projects.append({"slug": d.name, "project_name": d.name, "description": ""})
    return projects


def get_project_status(slug: str, workspace: str = "") -> str:
    ws = Path(workspace) if workspace else WORKSPACE_DIR
    project_dir = ws / slug
    if not project_dir.exists():
        return f"Project '{slug}' not found."

    manifest_path = project_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"project_name": slug, "slug": slug, "description": "", "tech_stack": "", "phases": []}

    lines = [f"Project: {manifest.get('project_name', slug)}"]
    if manifest.get("description"):
        lines.append(f"  Description: {manifest['description']}")
    if manifest.get("tech_stack"):
        lines.append(f"  Tech Stack: {manifest['tech_stack']}")

    lines.append("  Phases:")
    for role in ROLES:
        role_dir = project_dir / role["name"]
        status = "✓" if role_dir.exists() and any(role_dir.iterdir()) else "○"
        lines.append(f"    {status} {role['label']}")

    return "\n".join(lines)


def scaffold_project(
    parameters: dict[str, Any] | None = None,
    speak: Callable | None = None,
    player=None,
) -> str:
    p = parameters or {}
    project_name = p.get("project_name", "").strip()
    description = p.get("description", "").strip()
    tech_stack = p.get("tech_stack", "python").strip()
    workspace = p.get("workspace", "")
    roles = p.get("roles", ["project_manager", "backend", "frontend", "tester"])

    if not project_name:
        return "Please provide a project name, sir."

    if player:
        player.write_log(f"[Scaffold] Starting project: {project_name}")

    return start_project(
        project_name=project_name,
        description=description,
        tech_stack=tech_stack,
        workspace=workspace,
        roles=roles,
        speak=speak,
    )
