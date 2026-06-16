import logging
import os
import platform
import subprocess
import sys
from typing import Any

logger = logging.getLogger("package_manager")


def install_package(package: str, manager: str = "auto") -> dict[str, Any]:
    mgr = _detect_manager(manager)
    if mgr.startswith("pip"):
        return _run_pip(package, mgr)
    return _run_system(package, mgr)


def uninstall_package(package: str, manager: str = "auto") -> dict[str, Any]:
    mgr = _detect_manager(manager)
    if mgr.startswith("pip"):
        return _run_pip_uninstall(package, mgr)
    return _run_system_uninstall(package, mgr)


def list_installed(manager: str = "auto") -> list[dict[str, Any]]:
    mgr = _detect_manager(manager)
    if mgr == "pip":
        return _list_pip()
    elif mgr == "poetry":
        return _list_poetry()
    elif mgr == "uv":
        return _list_uv()
    else:
        return _list_system(mgr)


def update_all(manager: str = "auto") -> dict[str, Any]:
    mgr = _detect_manager(manager)
    if mgr.startswith("pip"):
        return _update_pip(mgr)
    return _update_system(mgr)


def _detect_manager(preferred: str) -> str:
    if preferred and preferred != "auto":
        return preferred

    _OS = platform.system()
    if _OS == "Linux":
        for cmd in ["apt", "dnf", "pacman", "zypper", "apk"]:
            if _which(cmd):
                return cmd
        return "pip"
    elif _OS == "Darwin":
        if _which("brew"):
            return "brew"
        return "pip"
    elif _OS == "Windows":
        if _which("winget"):
            return "winget"
        if _which("choco"):
            return "choco"
        return "pip"
    return "pip"


def _which(cmd: str) -> bool:
    try:
        proc = subprocess.run(["which", cmd] if platform.system() != "Windows"
                              else ["where", cmd],
                              capture_output=True, timeout=5)
        return proc.returncode == 0
    except Exception:
        return False


# ── Python package managers ────────────────────────────────────────────

def _run_pip(package: str, mgr: str) -> dict[str, Any]:
    python = sys.executable
    try:
        proc = subprocess.run(
            [python, "-m", "pip", "install", package],
            capture_output=True, text=True, timeout=120,
        )
        return {
            "success": proc.returncode == 0,
            "manager": mgr,
            "package": package,
            "output": proc.stdout[-500:] + proc.stderr[-500:],
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "manager": mgr, "package": package, "output": "Timed out"}


def _run_pip_uninstall(package: str, mgr: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", package],
            capture_output=True, text=True, timeout=30,
        )
        return {"success": proc.returncode == 0, "manager": mgr, "package": package}
    except subprocess.TimeoutExpired:
        return {"success": False, "manager": mgr, "package": package, "output": "Timed out"}


def _list_pip() -> list[dict[str, Any]]:
    try:
        import pkg_resources
        return [
            {"name": p.key, "version": p.version, "manager": "pip"}
            for p in pkg_resources.working_set
        ]
    except Exception:
        return []


def _list_poetry() -> list[dict[str, Any]]:
    try:
        proc = subprocess.run(
            ["poetry", "show"],
            capture_output=True, text=True, timeout=30,
        )
        pkgs = []
        for line in proc.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 2:
                pkgs.append({"name": parts[0], "version": parts[1], "manager": "poetry"})
        return pkgs
    except Exception:
        return []


def _list_uv() -> list[dict[str, Any]]:
    try:
        proc = subprocess.run(
            ["uv", "pip", "list"],
            capture_output=True, text=True, timeout=30,
        )
        pkgs = []
        for line in proc.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 2 and " " not in parts[0]:
                pkgs.append({"name": parts[0], "version": parts[1], "manager": "uv"})
        return pkgs
    except Exception:
        return []


def _update_pip(mgr: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
            capture_output=True, text=True, timeout=60,
        )
        return {"success": proc.returncode == 0, "manager": mgr, "output": "pip updated"}
    except subprocess.TimeoutExpired:
        return {"success": False, "manager": mgr, "output": "Timed out"}


# ── System package managers ────────────────────────────────────────────

SYSTEM_CMDS = {
    "apt": {"install": ["apt", "install", "-y"], "uninstall": ["apt", "remove", "-y"],
            "list": ["apt", "list", "--installed"], "update": ["apt", "update"]},
    "dnf": {"install": ["dnf", "install", "-y"], "uninstall": ["dnf", "remove", "-y"],
            "list": ["dnf", "list", "installed"], "update": ["dnf", "upgrade", "-y"]},
    "pacman": {"install": ["pacman", "-S", "--noconfirm"], "uninstall": ["pacman", "-R", "--noconfirm"],
               "list": ["pacman", "-Q"], "update": ["pacman", "-Syu", "--noconfirm"]},
    "brew": {"install": ["brew", "install"], "uninstall": ["brew", "uninstall"],
             "list": ["brew", "list"], "update": ["brew", "upgrade"]},
    "winget": {"install": ["winget", "install", "--silent"], "uninstall": ["winget", "uninstall", "--silent"],
               "list": ["winget", "list"], "update": ["winget", "upgrade", "--all"]},
    "choco": {"install": ["choco", "install", "-y"], "uninstall": ["choco", "uninstall", "-y"],
              "list": ["choco", "list"], "update": ["choco", "upgrade", "-y"]},
}


def _run_system(package: str, mgr: str) -> dict[str, Any]:
    cmds = SYSTEM_CMDS.get(mgr)
    if not cmds:
        return {"success": False, "manager": mgr, "output": f"Unknown manager: {mgr}"}
    try:
        proc = subprocess.run(
            [*cmds["install"], package],
            capture_output=True, text=True, timeout=300,
        )
        return {"success": proc.returncode == 0, "manager": mgr, "package": package}
    except subprocess.TimeoutExpired:
        return {"success": False, "manager": mgr, "output": "Timed out"}
    except FileNotFoundError:
        return {"success": False, "manager": mgr, "output": f"{mgr} not found on system"}


def _run_system_uninstall(package: str, mgr: str) -> dict[str, Any]:
    cmds = SYSTEM_CMDS.get(mgr)
    if not cmds:
        return {"success": False, "output": f"Unknown manager: {mgr}"}
    try:
        proc = subprocess.run(
            [*cmds["uninstall"], package],
            capture_output=True, text=True, timeout=120,
        )
        return {"success": proc.returncode == 0, "manager": mgr, "package": package}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Timed out"}


def _list_system(mgr: str) -> list[dict[str, Any]]:
    cmds = SYSTEM_CMDS.get(mgr)
    if not cmds:
        return []
    try:
        proc = subprocess.run(cmds["list"], capture_output=True, text=True, timeout=30)
        pkgs = []
        for line in proc.stdout.strip().split("\n"):
            parts = line.split()
            if parts:
                pkgs.append({"name": parts[0], "version": parts[1] if len(parts) > 1 else "", "manager": mgr})
        return pkgs
    except Exception:
        return []


def _update_system(mgr: str) -> dict[str, Any]:
    cmds = SYSTEM_CMDS.get(mgr)
    if not cmds:
        return {"success": False, "output": f"Unknown manager: {mgr}"}
    try:
        proc = subprocess.run(
            cmds["update"], capture_output=True, text=True, timeout=300,
        )
        return {"success": proc.returncode == 0, "manager": mgr}
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Timed out"}


def detect_os_package_manager() -> str:
    pm = _detect_manager("auto")
    return pm
