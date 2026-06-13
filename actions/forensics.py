import json
import logging
import os
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("forensics")

CACHE_PATH = Path(__file__).resolve().parent.parent / "memory" / "forensics_cache.json"
_lock = threading.Lock()


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: dict):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _run_cmd(cmd: list[str], timeout: int = 30) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def file_history(days: int = 1, path: str = "") -> list[dict[str, Any]]:
    results = []
    search_path = path or os.path.expanduser("~")
    cutoff = time.time() - (days * 86400)

    try:
        import os as _os
        for root, dirs, files in os.walk(search_path):
            if any(hidden in root for hidden in [".git", "__pycache__", "node_modules", ".cache", ".npm"]):
                continue
            if len(results) >= 100:
                break
            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    mtime = os.path.getmtime(fpath)
                    ctime = os.path.getctime(fpath)
                    if mtime > cutoff or ctime > cutoff:
                        results.append({
                            "path": fpath,
                            "name": fname,
                            "modified": datetime.fromtimestamp(mtime).isoformat(),
                            "created": datetime.fromtimestamp(ctime).isoformat(),
                            "size": os.path.getsize(fpath),
                        })
                except Exception:
                    continue
    except Exception as e:
        logger.warning("file_history walk error: %s", e)

    results.sort(key=lambda x: x.get("modified", ""), reverse=True)
    return results[:100]


def process_history(days: int = 1) -> list[dict[str, Any]]:
    results = []
    try:
        platform = sys.platform
        if platform == "linux":
            output = _run_cmd(["ps", "aux", "--sort=-start_time"])
            lines = output.split("\n")
            if len(lines) > 1:
                for line in lines[1:51]:
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        pid = parts[1]
                        cpu = parts[2]
                        mem = parts[3]
                        cmd = parts[10][:80] if len(parts) > 10 else parts[-1][:80]
                        user = parts[0]
                        results.append({
                            "pid": pid,
                            "user": user,
                            "cpu": cpu,
                            "memory": mem,
                            "command": cmd,
                        })
        elif platform == "darwin":
            output = _run_cmd(["ps", "aux", "-r"])
            lines = output.split("\n")
            if len(lines) > 1:
                for line in lines[1:51]:
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        results.append({
                            "pid": parts[1],
                            "user": parts[0],
                            "cpu": parts[2],
                            "memory": parts[3],
                            "command": parts[10][:80] if len(parts) > 10 else parts[-1][:80],
                        })
        elif platform == "win32":
            output = _run_cmd(["tasklist", "/FO", "CSV", "/NH"])
            lines = output.split("\n")
            for line in lines[:50]:
                parts = line.strip().strip('"').split('","')
                if len(parts) >= 5:
                    results.append({
                        "name": parts[0],
                        "pid": parts[1],
                        "session": parts[2],
                        "memory": parts[4],
                    })
    except Exception as e:
        logger.warning("process_history error: %s", e)

    return results


def network_history(days: int = 1) -> list[dict[str, Any]]:
    results = []
    try:
        platform = sys.platform
        if platform == "linux":
            output = _run_cmd(["ss", "-tunapl"])
            if "Error" not in output:
                lines = output.split("\n")
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 5:
                        local = parts[3]
                        peer = parts[4]
                        state = parts[1] if len(parts) > 1 else "?"
                        results.append({
                            "local": local,
                            "peer": peer,
                            "state": state,
                        })
            else:
                output2 = _run_cmd(["netstat", "-tunapl"])
                if "Error" not in output2:
                    lines = output2.split("\n")
                    for line in lines[2:51]:
                        parts = line.split()
                        if len(parts) >= 5:
                            results.append({
                                "local": parts[3],
                                "peer": parts[4],
                                "state": parts[5] if len(parts) > 5 else "?",
                            })
        elif platform == "darwin":
            output = _run_cmd(["lsof", "-i", "-P", "-n"])
            lines = output.split("\n")
            for line in lines[1:51]:
                parts = line.split()
                if len(parts) >= 9:
                    results.append({
                        "command": parts[0],
                        "pid": parts[1],
                        "protocol": parts[4],
                        "local": parts[8] if len(parts) > 8 else "",
                    })
        elif platform == "win32":
            output = _run_cmd(["netstat", "-ano"])
            lines = output.split("\n")
            for line in lines[4:54]:
                parts = line.split()
                if len(parts) >= 4:
                    results.append({
                        "protocol": parts[0],
                        "local": parts[1],
                        "peer": parts[2],
                        "state": parts[3] if len(parts) > 3 else "",
                    })
    except Exception as e:
        logger.warning("network_history error: %s", e)

    return results


def what_installed_since(days: int = 1) -> str:
    platform = sys.platform
    results = []

    if platform == "linux":
        log_paths = [
            "/var/log/dpkg.log",
            "/var/log/apt/history.log",
            "/var/log/pacman.log",
            "/var/log/dnf.log",
        ]
        for lp in log_paths:
            log_file = Path(lp)
            if log_file.exists():
                cutoff = datetime.now() - timedelta(days=days)
                try:
                    text = log_file.read_text(encoding="utf-8", errors="ignore")
                    for line in text.split("\n"):
                        for keyword in ["install", "Installed", "upgrade", "remove"]:
                            if keyword in line:
                                results.append(line.strip())
                                break
                except Exception:
                    continue

        pip_output = _run_cmd([sys.executable, "-m", "pip", "list", "--format=columns"])
        if "Error" not in pip_output:
            results.append(f"\nCurrently installed pip packages:\n{pip_output[:2000]}")

    elif platform == "win32":
        wmic = _run_cmd(["wmic", "product", "get", "name,installdate"])
        if "Error" not in wmic:
            results.append(f"Installed programs:\n{wmic[:2000]}")

    elif platform == "darwin":
        brew = _run_cmd(["brew", "list", "--formula"])
        if "Error" not in brew:
            results.append(f"Brew formulae:\n{brew[:2000]}")

    if not results:
        results.append(f"No package install logs found for the last {days} day(s).")

    return "\n".join(results[:50])


def get_forensics_summary(days: int = 1) -> str:
    lines = [f"Forensics Report (last {days} day(s)):"]
    lines.append("")

    lines.append("--- Recent File Changes ---")
    files = file_history(days=days)
    if files:
        for f in files[:10]:
            lines.append(f"  [{f['modified'][:19]}] {f['name']} ({f['path'][:80]})")
    else:
        lines.append("  No recent file changes found.")

    lines.append("")
    lines.append("--- Top Processes ---")
    procs = process_history(days=days)
    if procs:
        for p in procs[:10]:
            cmd = p.get("command", p.get("name", p.get("pid", "?")))
            lines.append(f"  PID {p['pid']}: {cmd}")
    else:
        lines.append("  No process data available.")

    lines.append("")
    lines.append("--- Network Connections ---")
    nets = network_history(days=days)
    if nets:
        for n in nets[:10]:
            peer = n.get("peer", n.get("local", ""))
            state = n.get("state", "")
            extra = f" [{state}]" if state else ""
            lines.append(f"  {peer}{extra}")
    else:
        lines.append("  No network connection data available.")

    return "\n".join(lines)
