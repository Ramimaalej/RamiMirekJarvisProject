"""OpenCode integration — launch the open source AI coding agent from Jarvis.

Workflow:
  1. detect_opencode()  — is OpenCode installed? (PATH check)
  2. install_opencode() — installs via curl installer (Linux/macOS) or
                          tells the user how to install on Windows.
  3. run_opencode(prompt, directory) — runs `opencode run` non-interactively
     with the generated detailed dev prompt. Returns stdout text.

Usage from intent_router handler:
  opencode_action(parameters={"description": "a todo app",
                              "dir": "projects/todo"})
"""
import logging
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

logger = logging.getLogger("opencode")

INSTALL_URL = "https://opencode.ai/install"
_RUN_TIMEOUT = 600  # 10 min max for a code generation run

_CACHE: dict | None = None


def _which(name: str) -> str | None:
    return shutil.which(name)


def detect_opencode() -> dict:
    """Return {installed: bool, path, version}."""
    path = _which("opencode")
    if not path:
        return {"installed": False, "path": None, "version": None}
    version = None
    try:
        out = subprocess.run([path, "--version"], capture_output=True,
                             text=True, timeout=15).stdout.strip()
        version = out or None
    except Exception:  # noqa: BLE001
        pass
    return {"installed": True, "path": path, "version": version}


def install_opencode() -> str:
    """Install OpenCode. Returns a short human status message."""
    if detect_opencode()["installed"]:
        return "OpenCode is already installed."
    if sys.platform.startswith("win"):
        return ("OpenCode is not installed. On Windows, open PowerShell and run: "
                "npm i -g opencode-ai@latest   (or: scoop install opencode). "
                "Tell me again once it is installed.")
    try:
        req = urllib.request.Request(INSTALL_URL, headers={"User-Agent": "Jarvis/1.0"})
        script = urllib.request.urlopen(req, timeout=30).read()
        subprocess.run(["bash", "-c", "bash"], input=script,
                       capture_output=True, text=True, timeout=120)
        if detect_opencode()["installed"]:
            return "OpenCode installed successfully."
    except Exception as exc:  # noqa: BLE001
        logger.warning("opencode install error: %s", exc)
    return ("Could not install OpenCode automatically. Run this in your terminal: "
            "curl -fsSL https://opencode.ai/install | bash   then tell me again.")


def build_detailed_prompt(description: str, user_lang: str = "en") -> str:
    """Expand a short project idea into a high-detail dev prompt
    that OpenCode will execute autonomously."""
    detail = (
        "You are building a new development project from the following idea: {description}\n\n"
        "WORK AS AN AUTONOMOUS SENIOR DEVELOPER. Follow these steps in order:\n"
        "1. ANALYZE — restate requirements, list features (MVP + stretch goals), "
        "pick the most appropriate stack (framework, language, database) and justify it briefly.\n"
        "2. SCAFFOLD — create a clean project directory structure, init the project "
        "(npm/yarn/pnpm for JS, pip/poetry for Python, flutter create for mobile), "
        "and configure linting/formatting.\n"
        "3. IMPLEMENT — build the full MVP: core data models, API/backend logic if needed, "
        "routing, UI screens, state management, and error handling. Write real working code, "
        "not placeholders.\n"
        "4. TEST — add basic tests or at least verify the app runs; fix any errors you find.\n"
        "5. DOCUMENT — create a clear README.md with: project description, features, "
        "tech stack, installation steps, and how to run locally.\n\n"
        "RULES:\n"
        "- Prefer simple, modern, well-maintained libraries.\n"
        "- Code must run locally with a single documented command.\n"
        "- Commit nothing to git unless asked; keep everything inside the project folder.\n"
        "- Report what you built, where, and how to run it when finished.\n"
        "Respond in the same language as the user."
    ).format(description=description)
    return detail


def run_opencode(description: str, directory: str | None = None,
                 timeout: int = _RUN_TIMEOUT) -> str:
    """Run `opencode run` with a detailed prompt. Returns output text."""
    info = detect_opencode()
    if not info["installed"]:
        return "OpenCode is not installed on this machine. Say 'install opencode' to fix it."
    prompt = build_detailed_prompt(description)
    workdir = None
    if directory:
        workdir = Path(directory).expanduser()
        if workdir.is_dir():
            workdir = workdir
        else:
            workdir = Path.home() / "MyProjects" / Path(directory).name
            workdir.mkdir(parents=True, exist_ok=True)
    cmd = [info["path"], "run", prompt, "--auto"]
    if workdir:
        cmd += ["--dir", str(workdir)]
    logger.info("opencode run in %s (timeout %ss)", workdir, timeout)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              cwd=workdir)
        out = (proc.stdout or "") + (proc.stderr or "")
        out = re.sub(r"\x1b\[[0-9;]*m", "", out)  # strip ANSI colors
        return (out or "OpenCode finished with no output. Check the project folder: "
                       + str(workdir)).strip()[:4000]
    except subprocess.TimeoutExpired:
        return ("OpenCode is still working (it exceeded the time limit). "
                "It continues running in your terminal — check the project folder: " + str(workdir))
    except Exception as exc:  # noqa: BLE001
        return f"OpenCode run failed: {exc}. Make sure OpenCode is configured with a provider (opencode auth login)."


def opencode_action(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    action = (parameters.get("action") or "run").lower().strip()
    if action == "install":
        return install_opencode()
    if action == "status":
        info = detect_opencode()
        if info["installed"]:
            return (f"OpenCode is installed ({info['path']}, "
                    f"version {info['version'] or 'unknown'}). Ready to build projects.")
        return "OpenCode is not installed. Say 'install opencode' and I will set it up."
    description = parameters.get("description") or parameters.get("project") or ""
    if not description:
        return "Tell me what kind of project to build, for example: 'a todo app' or 'a portfolio website'."
    return run_opencode(description, parameters.get("dir"))
