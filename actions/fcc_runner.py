"""Free Claude Code launcher — run `fcc-server` + `fcc-claude` in a chosen folder.

User says:  "run free claude code in <folder>"
Jarvis:     1. finds the folder (path, home-relative, or by name search)
            2. opens the system terminal in that folder
            3. starts `fcc-server` in the background and `fcc-claude` up front
            4. keeps the terminal open so the user can keep working

Exported handler: ``run_fcc_in_folder(parameters=..., player=...)``
"""

from __future__ import annotations

import logging
import platform
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("fcc_runner")

_SYSTEM = platform.system()

# ── Folder search ────────────────────────────────────────────────────────
# Roots checked (in order) when the user gives a bare folder name.
_SEARCH_ROOTS = [
    "~/MyProjects",
    "~/Projects",
    "~/Documents",
    "~/workspace",
    "~/Desktop",
    "~/dev",
    "~",
]

_MAX_DIRS_SCANNED = 6000          # safety cap for the deep walk
_MAX_WALK_DEPTH    = 3


def find_folder(query: str) -> Path | None:
    """Locate a folder from a path or a bare name.

    Resolution order:
      1. ``query`` is an existing path (``~`` expanded, symlinks resolved).
      2. ``query`` is a sub-path of a known root (e.g. ``MyProjects/Jarvis``).
      3. ``query`` is a bare name found in a known root (exact, then substring,
         then fuzzy). Deep search up to ``_MAX_WALK_DEPTH`` levels.
    Returns the single best match, or ``None``.
    """
    if not query:
        return None
    q = query.strip().strip("\"'")

    # 1. Direct path
    try:
        p = Path(q).expanduser().resolve()
        if p.is_dir():
            return p
    except OSError:
        pass

    # 2. Path relative to a known root
    for root in _SEARCH_ROOTS:
        cand = (Path(root).expanduser() / q).resolve()
        if cand.is_dir():
            return cand

    # 3. Name search
    hits = _walk_search(q)
    if not hits:
        return None
    hits.sort(key=lambda p: (p.name.lower() != q.lower(), len(p.parts)))
    return hits[0]


def find_folders(query: str) -> list[Path]:
    """All folders matching ``query`` (for disambiguation / reporting)."""
    if not query:
        return []
    q = query.strip().strip("\"'")
    if not q:
        return []
    try:
        p = Path(q).expanduser().resolve()
        if p.is_dir():
            return [p]
    except OSError:
        pass
    hits = _walk_search(q)
    hits.sort(key=lambda p: (p.name.lower() != q.lower(), len(p.parts)))
    return hits


def _walk_search(query: str) -> list[Path]:
    """Bounded breadth-first search for a folder named like ``query``."""
    ql = query.lower()
    exact:  list[Path] = []
    fuzzy:  list[Path] = []
    visited = 0
    for root in _SEARCH_ROOTS:
        base = Path(root).expanduser()
        if not base.is_dir():
            continue
        stack: list[tuple[Path, int]] = [(base, 0)]
        while stack:
            d, depth = stack.pop()
            if depth > _MAX_WALK_DEPTH or visited > _MAX_DIRS_SCANNED:
                continue
            try:
                children = list(d.iterdir())
            except OSError:
                continue
            for child in children:
                if child.name.startswith(".") or child.is_symlink():
                    continue
                if not child.is_dir():
                    continue
                visited += 1
                cl = child.name.lower()
                if cl == ql:
                    exact.append(child.resolve())
                elif ql in cl:
                    fuzzy.append(child.resolve())
                stack.append((child, depth + 1))
            if visited > _MAX_DIRS_SCANNED:
                break
    return exact or fuzzy


# ── Terminal handling ────────────────────────────────────────────────────
# Maps terminal binary → argv template.  ``{dir}`` = working directory,
# ``{cmd}`` = command the shell should run.
_TERMINAL_TEMPLATES: dict[str, list[str]] = {
    "gnome-terminal": ["--working-directory={dir}", "--", "bash", "-lc", "{cmd}"],
    "konsole":        ["--workdir", "{dir}", "-e", "bash", "-lc", "{cmd}"],
    "xfce4-terminal": ["--working-directory={dir}", "-e", "bash", "-lc", "{cmd}"],
    "terminator":     ["--working-directory={dir}", "-e", "bash", "-lc", "{cmd}"],
    "alacritty":      ["--working-directory", "{dir}", "-e", "bash", "-lc", "{cmd}"],
    "kitty":          ["--working-directory={dir}", "bash", "-lc", "{cmd}"],
    "wezterm":        ["start", "--cwd", "{dir}", "bash", "-lc", "{cmd}"],
    "xterm":          ["-e", "bash", "-lc", "cd {dir} && {cmd}"],
    "uxterm":         ["-e", "bash", "-lc", "cd {dir} && {cmd}"],
}


def detect_terminal() -> str:
    """Return the system's default terminal emulator binary name."""
    if _SYSTEM != "Linux":
        return "gnome-terminal"
    try:
        gs = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.default-applications.terminal", "exec"],
            capture_output=True, text=True, timeout=5,
        )
        if gs.returncode == 0:
            term = gs.stdout.strip().strip("'")
            if term:
                return term
    except Exception:
        pass
    xdg = shutil.which("xdg-terminal")
    if xdg:
        return "xterm"
    for term in ["gnome-terminal", "konsole", "xfce4-terminal", "lxterminal",
                 "terminator", "alacritty", "kitty", "wezterm", "xterm",
                 "mate-terminal", "tilix", "sakura"]:
        if shutil.which(term):
            return term
    return "xterm"


def _shell_cmd(folder: Path) -> str:
    """Command run inside the terminal: server in background, Claude in front.

    Each process cd's into the folder explicitly so the command works even
    for terminals that ignore ``--working-directory``.
    """
    fcc_server = shutil.which("fcc-server") or "fcc-server"
    fcc_claude = shutil.which("fcc-claude") or "fcc-claude"
    quoted = str(folder).replace("'", "'\\''")
    return (
        f"cd '{quoted}' && {fcc_server} & "
        f"cd '{quoted}' && {fcc_claude}; exec bash"
    )


def open_terminal_in(folder: Path, command: str | None = None) -> bool:
    """Open the default terminal in ``folder`` running ``command``.

    Returns ``True`` on successful launch (does not wait for exit).
    """
    if not folder.is_dir():
        return False
    cmd = command if command is not None else _shell_cmd(folder)

    if _SYSTEM == "Darwin":
        script = (
            'tell application "Terminal"\n'
            f'  do script "cd {_apple_escape(str(folder))} && {cmd.replace(chr(34), chr(39))}"\n'
            "  activate\n"
            "end tell"
        )
        try:
            subprocess.Popen(["osascript", "-e", script],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            logger.debug("osascript terminal failed: %s", e)
            return False

    if _SYSTEM == "Windows":
        try:
            flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
            subprocess.Popen(
                ["cmd", "/k", f'cd /d "{folder}" && {cmd}'],
                creationflags=flags,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as e:
            logger.debug("cmd terminal failed: %s", e)
            return False

    # Linux
    term = detect_terminal()
    template = _TERMINAL_TEMPLATES.get(term) or _TERMINAL_TEMPLATES["gnome-terminal"]
    args = [a.replace("{dir}", str(folder)).replace("{cmd}", cmd) for a in template]
    try:
        subprocess.Popen(
            [term] + args,
            start_new_session=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        logger.debug("terminal %s failed: %s", term, e)
    return False


def _apple_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


# ── Public handler (called by main.py / intent router) ───────────────────
_DEFAULT_FOLDER = "~/MyProjects"


def run_fcc_in_folder(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """Find the requested folder, open a terminal there, run fcc-server+fcc-claude."""
    params = parameters or {}
    query = (
        params.get("folder")
        or params.get("folder_name")
        or params.get("path")
        or params.get("text")
        or ""
    ).strip()

    if not query:
        # No folder given — fall back to a remembered / default project folder.
        remembered = _remembered_folder()
        query = remembered or _DEFAULT_FOLDER

    folder = find_folder(query)

    if folder is None:
        matches = find_folders(query)
        if len(matches) > 1:
            names = ", ".join(str(p) for p in matches[:5])
            return (
                f"I found several folders matching '{query}': {names}. "
                "Say which one, or give the full path like ~/MyProjects/Jarvis."
            )
        return (
            f"Could not find a folder named '{query}'. "
            "Give the full path like ~/MyProjects/Jarvis, or 'run free claude code' to use your default."
        )

    _remember_folder(folder)

    if not (shutil.which("fcc-server") or shutil.which("fcc-claude")):
        return (
            "fcc-server / fcc-claude are not on your PATH. "
            "Install Free Claude Code first, then try again."
        )

    ok = open_terminal_in(folder)
    if not ok:
        return f"Could not open a terminal in {folder}."

    if player is not None:
        try:
            player.write_log(f"[fcc] {folder}")
        except Exception:
            pass

    return (
        f"Opened {folder.name} in a terminal and started fcc-server + fcc-claude. "
        "The terminal stays open — press Ctrl+C in it to stop."
    )


# ── Remember last folder so "run free claude code" reuses it ─────────────
_RECALL_FILE = Path(__file__).resolve().parent.parent / "memory" / "fcc_last_folder.txt"


def _remember_folder(folder: Path) -> None:
    try:
        _RECALL_FILE.parent.mkdir(parents=True, exist_ok=True)
        _RECALL_FILE.write_text(str(folder), encoding="utf-8")
    except OSError:
        pass


def _remembered_folder() -> str:
    try:
        if _RECALL_FILE.exists():
            v = _RECALL_FILE.read_text(encoding="utf-8").strip()
            if v and Path(v).expanduser().is_dir():
                return v
    except OSError:
        pass
    return ""
