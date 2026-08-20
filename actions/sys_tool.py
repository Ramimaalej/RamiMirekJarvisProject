"""Use system/networking tools directly based on the user's speech
(nmap, ping, traceroute, netstat, dig, whois, ipconfig/ifconfig, nslookup...).

Jarvis analyses what the user needs from the sentence and either RUNS the
tool (if installed) or PROPOSES to install it first.

Usage (via Jarvis intent `use_tool`):
    {"tool": "nmap", "args": "192.168.1.0/24"}
"""
from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess

logger = logging.getLogger("jarvis.sys_tool")

# Tools Jarvis knows how to run. value = (binary name on linux/macos, windows name or None)
_KNOWN_TOOLS: dict[str, tuple[str, str]] = {
    "nmap": ("nmap", "nmap"),
    "ping": ("ping", "ping"),
    "traceroute": ("traceroute", "tracert"),
    "tracert": ("traceroute", "tracert"),
    "netstat": ("ss", "netstat"),
    "dig": ("dig", "nslookup"),
    "nslookup": ("nslookup", "nslookup"),
    "whois": ("whois", "whois"),
    "ip": ("ip", "ipconfig"),          # windows fallback handled per-tool
    "ifconfig": ("ifconfig", "ipconfig"),
    "ipconfig": ("ip", "ipconfig"),
    "curl": ("curl", "curl"),
    "wget": ("wget", "curl"),
    "ssh": ("ssh", "ssh"),
    "git": ("git", "git"),
    "docker": ("docker", "docker"),
    "ffmpeg": ("ffmpeg", "ffmpeg"),
    "python": ("python3", "python"),
    "python3": ("python3", "python"),
    "node": ("node", "node"),
    "grep": ("grep", "findstr"),
    "find": ("find", "where"),
    "wc": ("wc", "powershell"),        # powershell fallback below
    "awk": ("awk", "powershell"),
    "sed": ("sed", "powershell"),
    "tar": ("tar", "tar"),
    "zip": ("zip", "powershell"),
    "unzip": ("unzip", "powershell"),
    "htop": ("htop", "taskmgr"),
    "top": ("top", "taskmgr"),
}

_SAFE_PATTERNS = [
    r"^(nmap|ping|traceroute|tracert|netstat|ss|dig|nslookup|whois|ip|ifconfig|ipconfig|curl|wget|ssh|git|docker|ffmpeg|python|python3|node|grep|find|wc|awk|sed|tar|zip|unzip|htop|top)\b",
]

_BANNED = [
    r"\b(format|mkfs|dd\s)\b",
    r"\brm\s+-rf?\s+/",
    r"\b(del|deltree)\b.*\*",
    r"\bshutdown\b",
]


def _bin_for(tool: str) -> str:
    is_win = platform.system().lower() == "windows"
    linux_bin, win_bin = _KNOWN_TOOLS[tool]
    pick = win_bin if is_win else linux_bin
    # Prefer whatever is actually on PATH
    if shutil.which(pick) is not None:
        return pick
    other = win_bin if not is_win else linux_bin
    if shutil.which(other) is not None:
        return other
    return pick


def _build_cmd(tool: str, args: str, os_name: str) -> str | None:
    bin_name = _bin_for(tool)
    args = args.strip()
    # Windows-specific mappings
    if os_name == "windows":
        if tool in ("ip", "ifconfig"):
            return "ipconfig" + (f" {args}" if args else "")
        if tool == "netstat":
            return "netstat" + (f" {args}" if args else "")
        if tool == "tracert":
            return "tracert" + (f" {args}" if args else "")
        if tool == "dig":
            return "nslookup" + (f" {args}" if args else "")
        if tool == "grep":
            return f'findstr {args}' if args else "findstr"
        if tool == "wget":
            return f"curl -O {args}" if args else "curl"
    cmd = bin_name
    if args:
        cmd = f"{cmd} {args}"
    return cmd


def use_tool(parameters: dict, player=None) -> str:
    """Run a system tool based on speech.

    parameters: {"tool": "nmap", "args": "192.168.1.0/24",
                 "target": "...", "query": "..."}
    """
    tool = (parameters.get("tool") or "").strip().lower()
    args = (parameters.get("args") or parameters.get("target") or parameters.get("query") or "").strip()

    if not tool or tool not in _KNOWN_TOOLS:
        return "I don't know that tool. I can use nmap, ping, traceroute, netstat, dig, whois, curl, ssh, git, docker and more."

    is_win = platform.system().lower() == "windows"
    os_name = "windows" if is_win else ("macos" if platform.system().lower() == "darwin" else "linux")

    # Safety check on the full command
    full = (tool + " " + args).lower()
    for pat in _BANNED:
        if re.search(pat, full, re.IGNORECASE):
            return "I cannot run that — it looks dangerous."

    # Locate the binary (install tool name hint for nmap which often missing)
    bin_name = _bin_for(tool)
    bin_on_path = shutil.which(bin_name) is not None or shutil.which(
        ("ipconfig" if is_win and tool in ("ip", "ifconfig") else bin_name)
    ) is not None
    if not bin_on_path:
        # On Linux, nmap-like tools need apt install; propose via install intent
        return (f"{tool.title()} is not installed on your {os_name} machine. "
                f"Say 'install {tool}' and I will install it for you.")

    cmd = _build_cmd(tool, args, os_name)
    if not cmd:
        return "I cannot do that."

    try:
        if os_name == "windows":
            res = subprocess.run(["cmd", "/c", cmd], capture_output=True, text=True, timeout=60)
        else:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return f"{tool.title()} is running — the command is taking more than 60s, it may continue in the background."
    except Exception as e:
        return f"{tool.title()} failed: {e}"

    out = (res.stdout or "").strip()
    err = (res.stderr or "").strip()
    if res.returncode != 0 and not out:
        return f"{tool.title()} returned an error: {err[:200]}"
    return f"[{tool}] {out[:1500]}"
