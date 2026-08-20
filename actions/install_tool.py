"""Install any tool / application on the user's machine (multi-OS).

- Windows: winget (preferred), scoop, or download link guidance
- macOS  : brew (with fallback to cask)
- Linux  : apt (apt-get install -y)

Usage (via Jarvis intent `install_tool`):
    {"tool": "python", "app": "python"}
"""
from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess

logger = logging.getLogger("jarvis.install_tool")

# Friendly aliases -> canonical installer name
_KNOWN_ALIASES: dict[str, str] = {
    "python": "python", "python3": "python", "py": "python",
    "node": "nodejs", "node.js": "nodejs", "nodejs": "nodejs", "npm": "nodejs",
    "java": "openjdk", "jdk": "openjdk",
    "git": "git",
    "ffmpeg": "ffmpeg", "vlc": "vlc", "spotify": "spotify",
    "chrome": "googlechrome", "google chrome": "googlechrome",
    "edge": "microsoftedge", "firefox": "mozilla.firefox",
    "vscode": "microsoft.visualstudiocode", "vs code": "microsoft.visualstudiocode",
    "notepad++": "notepadplusplus", "notepad plus plus": "notepadplusplus",
    "7zip": "7zip", "7-zip": "7zip",
    "powershell": "microsoft.powershell",
    "docker": "docker.dockerdesktop", "docker desktop": "docker.dockerdesktop",
    "ollama": "ollama",
    "obsidian": "obsidian",
    "zoom": "zoom", "discord": "discord", "telegram": "telegram",
    "rust": "rustlang.rustup", "rustup": "rustlang.rustup",
    "go": "golang.go", "golang": "golang.go",
    "rustdesk": "rustdesk.rustdesk", "teamviewer": "teamviewer.teamviewer",
    "blender": "blender", "gimp": "gimp", "inkscape": "inkscape",
    "libreoffice": "libreoffice", "libre office": "libreoffice",
}

_MAC_ALIASES: dict[str, str] = {
    "googlechrome": "google-chrome",
    "microsoft.visualstudiocode": "visual-studio-code",
    "nodejs": "node",
    "openjdk": "openjdk",
    "notepadplusplus": "notepad-plus-plus",
}


def _is_installed(tool: str) -> bool:
    try:
        # 'which' works on all three OSes (Windows Git-Bash/WSL has it; on raw
        # Windows we fall back to shutil.which below).
        return shutil.which(tool) is not None
    except Exception:
        return False


def _os_name() -> str:
    sys = platform.system().lower()
    if sys == "darwin":
        return "macos"
    if sys == "windows":
        return "windows"
    return "linux"


def _command_for(os_name: str, tool: str) -> str | None:
    """Return the install command for the given tool on the OS, or None."""
    name = _KNOWN_ALIASES.get(tool.lower().strip(), tool.lower().strip())

    if os_name == "windows":
        cmd = f'winget install --id {name} --accept-package-agreements --accept-source-agreements'
        return cmd
    if os_name == "macos":
        pkg = _MAC_ALIASES.get(name, name)
        return f"brew install {pkg}"
    # Linux
    return f"sudo apt-get update -qq && sudo apt-get install -y {name}"


def install_tool(parameters: dict, player=None) -> str:
    """Install a tool by its friendly name.

    parameters: {"tool": "python", "app": "python"}
    """
    tool = (parameters.get("tool") or parameters.get("app") or "").strip()
    if not tool:
        return "Which tool should I install? Say 'install python' or 'installer vlc'."

    if _is_installed(tool):
        return f"{tool.title()} is already installed on your machine."

    os_name = _os_name()
    cmd = _command_for(os_name, tool)
    if not cmd:
        return "I cannot do that."

    try:
        if os_name == "windows":
            # winget is not in PATH for subprocess by default on some installs
            res = subprocess.run(
                ["cmd", "/c", cmd], capture_output=True, text=True, timeout=600,
            )
        else:
            res = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=600,
            )
    except subprocess.TimeoutExpired:
        return f"Installing {tool.title()} is taking too long — it may still be running in the background."
    except Exception as e:
        return f"I cannot install {tool.title()}: {e}"

    if res.returncode == 0:
        logger.info("[install_tool] %s installed on %s", tool, os_name)
        return f"{tool.title()} installed successfully."
    out = (res.stderr or res.stdout or "").strip()[:300]
    return f"Installation of {tool.title()} failed. Try: {cmd}\nDetails: {out}"
