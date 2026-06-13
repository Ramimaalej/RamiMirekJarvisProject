import logging
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("file_search")

_OS = platform.system()


def search_files(
    query: str,
    root: str | None = None,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    if _OS == "Windows":
        return _search_everything(query, max_results)
    return _search_linux(query, root, max_results)


def _search_linux(query: str, root: str | None, max_results: int) -> list[dict[str, Any]]:
    root = root or str(Path.home())
    results = []
    try:
        proc = subprocess.run(
            ["locate", "-i", "-l", str(max_results), query],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            for line in proc.stdout.strip().split("\n"):
                if line and len(results) < max_results:
                    p = Path(line)
                    if p.exists():
                        results.append(_file_info(p))
            if results:
                return results
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    try:
        import glob
        matches = []
        patterns = [
            f"**/*{query}*",
            f"**/*{query.lower()}*",
            f"**/*{query.upper()}*",
        ]
        for p in patterns:
            matches.extend(
                str(x) for x in Path(root).rglob(p)
                if x.is_file() and len(matches) < max_results
            )
        for m in matches[:max_results]:
            results.append(_file_info(Path(m)))
    except Exception as e:
        logger.warning("glob search error: %s", e)

    return results


def _search_everything(query: str, max_results: int) -> list[dict[str, Any]]:
    try:
        proc = subprocess.run(
            ["es", query, "-n", str(max_results)],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            results = []
            for line in proc.stdout.strip().split("\n"):
                if line and len(results) < max_results:
                    p = Path(line)
                    if p.exists():
                        results.append(_file_info(p))
            return results
    except FileNotFoundError:
        pass

    try:
        from everything import Everything
        ev = Everything()
        ev.search(query)
        results = []
        for item in ev.results[:max_results]:
            results.append({
                "name": item.filename or "",
                "path": item.full_path or "",
                "size": item.size or 0,
                "modified": str(item.date_modified) if item.date_modified else "",
            })
        return results
    except ImportError:
        logger.info("Everything SDK not available — falling back to os.walk")
    except Exception as e:
        logger.warning("Everything search error: %s", e)

    return _fallback_windows_search(query, max_results)


def _fallback_windows_search(query: str, max_results: int) -> list[dict[str, Any]]:
    results = []
    search_dirs = [
        Path.home() / "Desktop",
        Path.home() / "Documents",
        Path.home() / "Downloads",
    ]
    for d in search_dirs:
        if not d.exists():
            continue
        try:
            for p in d.rglob(f"*{query}*"):
                if p.is_file() and len(results) < max_results:
                    results.append(_file_info(p))
        except PermissionError:
            continue
    return results


def _file_info(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
        return {
            "name": path.name,
            "path": str(path.resolve()),
            "size": stat.st_size,
            "modified": str(path.stat().st_mtime),
            "extension": path.suffix.lower(),
            "is_dir": path.is_dir(),
        }
    except Exception:
        return {"name": path.name, "path": str(path), "error": "stat failed"}
