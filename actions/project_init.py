import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("project_init")

WORKSPACE_DIR = Path(__file__).resolve().parent.parent / "workspace"

_PROJECT_TYPES = {
    "python": {
        "label": "Python",
        "ext": "py",
        "files": ["main.py", "requirements.txt", "README.md"],
    },
    "react": {
        "label": "React (Vite)",
        "ext": "jsx",
        "vite": True,
        "template": "react",
    },
    "react-ts": {
        "label": "React + TypeScript (Vite)",
        "ext": "tsx",
        "vite": True,
        "template": "react-ts",
    },
    "nextjs": {
        "label": "Next.js",
        "ext": "jsx",
        "next": True,
    },
    "nextjs-ts": {
        "label": "Next.js + TypeScript",
        "ext": "tsx",
        "next": True,
        "typescript": True,
    },
    "web": {
        "label": "Web Design (HTML/CSS/JS)",
        "ext": "html",
        "files": ["index.html", "style.css", "script.js", "README.md"],
    },
    "node": {
        "label": "Node.js",
        "ext": "js",
        "files": ["index.js", "package.json", "README.md"],
    },
    "express": {
        "label": "Express.js",
        "ext": "js",
        "files": ["index.js", "package.json", "routes/example.js", "README.md"],
    },
    "fastapi": {
        "label": "FastAPI",
        "ext": "py",
        "files": ["main.py", "requirements.txt", "README.md"],
    },
    "flask": {
        "label": "Flask",
        "ext": "py",
        "files": ["app.py", "requirements.txt", "README.md"],
    },
    "vanilla": {
        "label": "Vanilla JS",
        "ext": "js",
        "files": ["index.html", "app.js", "style.css"],
    },
    "vue": {
        "label": "Vue (Vite)",
        "ext": "vue",
        "vite": True,
        "template": "vue",
    },
    "svelte": {
        "label": "Svelte (Vite)",
        "ext": "svelte",
        "vite": True,
        "template": "svelte",
    },
    "rust": {
        "label": "Rust",
        "ext": "rs",
        "cargo": True,
    },
    "go": {
        "label": "Go",
        "ext": "go",
        "files": ["main.go", "go.mod", "README.md"],
    },
}

_TEMPLATES: dict[str, dict[str, str]] = {
    "python": {
        "main.py": "def main():\n    print(\"Hello, World!\")\n\n\nif __name__ == \"__main__\":\n    main()\n",
        "requirements.txt": "# Dependencies\n# pip install -r requirements.txt\n",
        "README.md": "# {name}\n\n## Setup\n```bash\npython -m venv venv\nsource venv/bin/activate\npip install -r requirements.txt\n```\n\n## Run\n```bash\npython main.py\n```\n",
    },
    "web": {
        "index.html": "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n    <meta charset=\"UTF-8\">\n    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n    <title>{name}</title>\n    <link rel=\"stylesheet\" href=\"style.css\">\n</head>\n<body>\n    <h1>{name}</h1>\n    <script src=\"script.js\"></script>\n</body>\n</html>\n",
        "style.css": "* {\n    margin: 0;\n    padding: 0;\n    box-sizing: border-box;\n}\n\nbody {\n    font-family: system-ui, -apple-system, sans-serif;\n    line-height: 1.6;\n    color: #333;\n    max-width: 800px;\n    margin: 0 auto;\n    padding: 2rem;\n}\n",
        "script.js": "document.addEventListener('DOMContentLoaded', () => {\n    console.log('{name} loaded');\n});\n",
        "README.md": "# {name}\n\nA web design project.\n",
    },
    "node": {
        "index.js": "const express = require('express');\n\nconst app = express();\nconst PORT = process.env.PORT || 3000;\n\napp.get('/', (req, res) => {\n    res.json({ message: 'Hello from {name}!' });\n});\n\napp.listen(PORT, () => {\n    console.log(`Server running on port ${PORT}`);\n});\n",
        "package.json": '{\n  "name": "{slug}",\n  "version": "1.0.0",\n  "description": "{description}",\n  "main": "index.js",\n  "scripts": {\n    "start": "node index.js",\n    "dev": "node --watch index.js"\n  },\n  "dependencies": {\n    "express": "^4.18.0"\n  }\n}\n',
        "README.md": "# {name}\n\n## Setup\n```bash\nnpm install\n```\n\n## Run\n```bash\nnpm start\n```\n",
    },
    "express": {
        "index.js": "const express = require('express');\nconst path = require('path');\n\nconst app = express();\nconst PORT = process.env.PORT || 3000;\n\napp.use(express.json());\napp.use(express.urlencoded({ extended: true }));\n\nconst exampleRouter = require('./routes/example');\napp.use('/api', exampleRouter);\n\napp.listen(PORT, () => {\n    console.log(`Server running on port ${PORT}`);\n});\n",
        "package.json": '{\n  "name": "{slug}",\n  "version": "1.0.0",\n  "description": "{description}",\n  "main": "index.js",\n  "scripts": {\n    "start": "node index.js",\n    "dev": "node --watch index.js"\n  },\n  "dependencies": {\n    "express": "^4.18.0"\n  }\n}\n',
        "routes/example.js": "const express = require('express');\nconst router = express.Router();\n\nrouter.get('/hello', (req, res) => {\n    res.json({ message: 'Hello from Express!' });\n});\n\nmodule.exports = router;\n",
        "README.md": "# {name}\n\nExpress.js API server.\n",
    },
    "fastapi": {
        "main.py": "from fastapi import FastAPI\n\napp = FastAPI(title=\"{name}\")\n\n\n@app.get(\"/\")\nasync def root():\n    return {\"message\": \"Hello from {name}!\"}\n\n\n@app.get(\"/health\")\nasync def health():\n    return {\"status\": \"ok\"}\n",
        "requirements.txt": "fastapi\nuvicorn\n",
        "README.md": "# {name}\n\n## Setup\n```bash\npython -m venv venv\nsource venv/bin/activate\npip install -r requirements.txt\n```\n\n## Run\n```bash\nuvicorn main:app --reload\n```\n",
    },
    "flask": {
        "app.py": "from flask import Flask\n\napp = Flask(__name__)\n\n\n@app.route('/')\ndef home():\n    return {\"message\": \"Hello from {name}!\"}\n\n\nif __name__ == '__main__':\n    app.run(debug=True)\n",
        "requirements.txt": "flask\n",
        "README.md": "# {name}\n\n## Setup\n```bash\npython -m venv venv\nsource venv/bin/activate\npip install -r requirements.txt\n```\n\n## Run\n```bash\npython app.py\n```\n",
    },
    "vanilla": {
        "index.html": "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n    <meta charset=\"UTF-8\">\n    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n    <title>{name}</title>\n</head>\n<body>\n    <h1>{name}</h1>\n    <script src=\"app.js\"></script>\n</body>\n</html>\n",
        "app.js": "console.log('{name} loaded');\n",
        "style.css": "body { font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 2rem; }\n",
    },
    "go": {
        "main.go": "package main\n\nimport \"fmt\"\n\nfunc main() {\n    fmt.Println(\"Hello from {name}!\")\n}\n",
        "go.mod": "module {slug}\n\ngo 1.21\n",
        "README.md": "# {name}\n\n## Setup\n```bash\ngo mod tidy\n```\n\n## Run\n```bash\ngo run main.go\n```\n",
    },
}

_GITIGNORE: dict[str, str] = {
    "python": "venv/\n__pycache__/\n*.pyc\n.env\n*.egg-info/\ndist/\nbuild/\n",
    "node": "node_modules/\n.env\ndist/\nbuild/\n.DS_Store\n",
    "react": "node_modules/\n.env\ndist/\n.DS_Store\n",
    "nextjs": "node_modules/\n.env\n.next/\nout/\n.DS_Store\n",
    "go": "bin/\n.DS_Store\n",
    "rust": "target/\n.DS_Store\n",
    "default": "node_modules/\n.env\n.DS_Store\n__pycache__/\n",
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\-]", "-", name.lower()).strip("-") or "project"


def _check_command(cmd: str) -> bool:
    try:
        r = subprocess.run(["which", cmd], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 120) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode, out.strip()
    except subprocess.TimeoutExpired:
        return -1, "Command timed out."
    except Exception as e:
        return -1, str(e)


def _install_deps(project_dir: Path, project_type: str) -> str:
    msgs = []
    if project_type in ("node", "express"):
        if _check_command("npm"):
            code, out = _run(["npm", "install"], cwd=project_dir)
            if code == 0:
                msgs.append("npm dependencies installed.")
            else:
                msgs.append(f"npm install had issues:\n{out[:200]}")
        else:
            msgs.append("npm not found — install Node.js first.")
    elif project_type == "python":
        if _check_command("pip3") or _check_command("pip"):
            pip = "pip3" if _check_command("pip3") else "pip"
            code, out = _run([pip, "install", "-r", "requirements.txt"], cwd=project_dir)
            if code == 0:
                msgs.append("Python dependencies installed.")
            else:
                msgs.append(f"pip install had issues:\n{out[:200]}")
        else:
            msgs.append("pip not found.")
    elif project_type in ("go",):
        if _check_command("go"):
            code, out = _run(["go", "mod", "tidy"], cwd=project_dir)
            if code == 0:
                msgs.append("Go dependencies tidied.")
            else:
                msgs.append(f"go mod tidy had issues:\n{out[:200]}")
    return "\n".join(msgs)


def _create_gitignore(project_dir: Path, project_type: str):
    gitignore = _GITIGNORE.get(project_type, _GITIGNORE["default"])
    (project_dir / ".gitignore").write_text(gitignore)


def _write_template(project_dir: Path, name: str, template_key: str, slug: str, description: str):
    templates = _TEMPLATES.get(template_key, {})
    for filepath_rel, content in templates.items():
        fp = project_dir / filepath_rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(
            content.format(name=name, slug=slug, description=description or name)
        )


def _write_manifest(project_dir: Path, name: str, slug: str, project_type: str, description: str):
    import json
    manifest = {
        "project_name": name,
        "slug": slug,
        "type": project_type,
        "description": description,
        "created": __import__("datetime").datetime.now().isoformat(),
    }
    (project_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


def init_project(
    project_name: str,
    project_type: str = "web",
    description: str = "",
    workspace: str = "",
    install_deps: bool = True,
    git_init: bool = True,
) -> str:
    ws = Path(workspace) if workspace else WORKSPACE_DIR
    ws.mkdir(parents=True, exist_ok=True)

    slug = _slug(project_name)
    project_dir = ws / slug

    if project_dir.exists():
        return f"Project '{slug}' already exists at {project_dir}."

    proj = _PROJECT_TYPES.get(project_type)
    if not proj:
        types = ", ".join(sorted(_PROJECT_TYPES))
        return f"Unknown type '{project_type}'. Available: {types}"

    lines = [f"Creating {proj['label']} project '{project_name}'..."]

    # ── Create via Vite ─────────────────────────────────────────────────────
    if proj.get("vite"):
        if _check_command("npm"):
            lines.append("Scaffolding with Vite...")
            code, out = _run([
                "npm", "create", "vite@latest", slug,
                "--", "--template", proj["template"],
            ], cwd=ws, timeout=60)
            if code != 0:
                lines.append(f"Vite scaffolding failed:\n{out[:300]}")
                return "\n".join(lines)
            lines.append("Vite project created.")
        else:
            lines.append("npm not found — falling back to manual template.")

    # ── Create via create-next-app ──────────────────────────────────────────
    elif proj.get("next"):
        if _check_command("npx"):
            lines.append("Scaffolding Next.js...")
            ts_flag = "--typescript" if proj.get("typescript") else "--javascript"
            code, out = _run([
                "npx", "create-next-app@latest", slug,
                ts_flag, "--eslint", "--tailwind", "--app", "--no-src-dir",
                "--import-alias", "@/*",
            ], cwd=ws, timeout=120)
            if code != 0:
                lines.append(f"Next.js scaffolding failed:\n{out[:300]}")
                return "\n".join(lines)
            lines.append("Next.js project created.")
        else:
            lines.append("npx not found — falling back to manual template.")

    # ── Create via Cargo ────────────────────────────────────────────────────
    elif proj.get("cargo"):
        if _check_command("cargo"):
            lines.append("Creating Rust project with Cargo...")
            code, out = _run(["cargo", "new", slug], cwd=ws, timeout=60)
            if code != 0:
                lines.append(f"Cargo failed:\n{out[:200]}")
                return "\n".join(lines)
            lines.append("Rust project created.")
        else:
            lines.append("Cargo not found.")

    # ── Manual template ─────────────────────────────────────────────────────
    else:
        project_dir.mkdir(parents=True, exist_ok=True)
        _write_template(project_dir, project_name, project_type, slug, description)
        lines.append("Project files created.")
        _create_gitignore(project_dir, project_type)
        lines.append(".gitignore created.")

    # ── Always write manifest ───────────────────────────────────────────────
    _write_manifest(project_dir, project_name, slug, project_type, description)

    # ── Git init ────────────────────────────────────────────────────────────
    if git_init and _check_command("git"):
        code, out = _run(["git", "init"], cwd=project_dir)
        if code == 0:
            lines.append("Git repository initialized.")
        code, out = _run(["git", "add", "-A"], cwd=project_dir)
        code, out = _run(["git", "commit", "-m", "Initial commit"], cwd=project_dir)
        if code == 0:
            lines.append("Initial commit made.")

    # ── Install dependencies ────────────────────────────────────────────────
    if install_deps:
        dep_msg = _install_deps(project_dir, project_type)
        if dep_msg:
            lines.append(dep_msg)

    lines.append(f"Project ready at {project_dir}")
    return "\n".join(lines)


def clone_repo(
    git_url: str,
    target_dir: str = "",
    workspace: str = "",
    install_deps: bool = True,
) -> str:
    if not _check_command("git"):
        return "Git is not installed."

    ws = Path(workspace) if workspace else WORKSPACE_DIR
    ws.mkdir(parents=True, exist_ok=True)

    target = Path(target_dir) if target_dir else ws
    if not target.is_absolute():
        target = ws / target

    lines = [f"Cloning {git_url}..."]

    # Extract repo name for display
    repo_name = git_url.rstrip("/").split("/")[-1].replace(".git", "")

    code, out = _run(["git", "clone", git_url, str(target / repo_name)], timeout=120)
    if code != 0:
        return f"Clone failed:\n{out[:500]}"

    project_dir = target / repo_name
    lines.append(f"Cloned into {project_dir}")

    # Detect project type
    detected = _detect_project_type(project_dir)
    if detected:
        lines.append(f"Detected: {_PROJECT_TYPES.get(detected, {}).get('label', detected)}")

    # Install dependencies
    if install_deps and detected:
        dep_msg = _install_deps(project_dir, detected)
        if dep_msg:
            lines.append(dep_msg)

    # Write manifest
    _write_manifest(project_dir, repo_name, _slug(repo_name), detected or "unknown", f"Cloned from {git_url}")

    lines.append(f"Repository ready at {project_dir}")
    return "\n".join(lines)


def _detect_project_type(project_dir: Path) -> str | None:
    files = set(f.name for f in project_dir.iterdir() if f.is_file())

    if "package.json" in files:
        try:
            import json
            pkg = json.loads((project_dir / "package.json").read_text(encoding="utf-8"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "next" in deps:
                return "nextjs"
            if "react" in deps:
                return "react"
            if "vue" in deps:
                return "vue"
            if "svelte" in deps:
                return "svelte"
            if "express" in deps:
                return "express"
            return "node"
        except Exception:
            return "node"

    if "Cargo.toml" in files:
        return "rust"
    if "go.mod" in files:
        return "go"
    if "requirements.txt" in files or "setup.py" in files or "pyproject.toml" in files:
        return "python"
    if "setup.cfg" in files:
        return "python"
    if any(f.endswith(".py") for f in files):
        return "python"
    if "index.html" in files or any(f.endswith(".html") for f in files):
        return "web"
    if "composer.json" in files:
        return "php"

    dirs = set(d.name for d in project_dir.iterdir() if d.is_dir())
    if "src" in dirs and "node_modules" in dirs:
        return "react"

    return None


def handle(parameters: dict[str, Any] | None = None, **kwargs) -> str:
    p = parameters or {}
    mode = p.get("mode", "create").strip().lower()

    if mode == "create":
        return init_project(
            project_name=p.get("project_name", "").strip(),
            project_type=p.get("project_type", "web").strip().lower(),
            description=p.get("description", "").strip(),
            workspace=p.get("workspace", ""),
            install_deps=p.get("install_deps", True),
            git_init=p.get("git_init", True),
        )

    elif mode == "clone":
        return clone_repo(
            git_url=p.get("git_url", "").strip(),
            target_dir=p.get("target_dir", "").strip(),
            workspace=p.get("workspace", ""),
            install_deps=p.get("install_deps", True),
        )

    elif mode == "list":
        from actions.project_scaffold import list_projects
        projects = list_projects(workspace=p.get("workspace", ""))
        if not projects:
            return "No projects found."
        lines = ["Projects:"]
        for pr in projects:
            lines.append(f"  {pr.get('project_name', pr.get('slug', '?'))}  ({pr.get('type', pr.get('tech_stack', '?'))})")
        return "\n".join(lines)

    elif mode == "types":
        lines = ["Available project types:"]
        for key, val in _PROJECT_TYPES.items():
            lines.append(f"  {key:12s}  {val['label']}")
        return "\n".join(lines)

    return "Unknown mode. Use: create, clone, list, or types."
