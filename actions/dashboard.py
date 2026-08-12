"""Daily Dashboard — Jarvis knows your daily software and opens it all on demand.

Storage: ``memory/dashboard.json``
   {
     "apps":  ["chrome", "vscode", "whatsapp"],   # order = launch order
     "usage": {"chrome": ["2026-08-01", "2026-08-02"], ...},
   }

User says:  "open my dashboard"  → open every app in ``apps`` (in order).
            "add X to my dashboard" / "remove X from my dashboard"
            "what's on my dashboard"
Jarvis also learns on its own: every time ``open_app`` successfully launches
an app, ``log_usage`` records the day. Apps opened on several distinct days
are promoted to the dashboard automatically.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger("dashboard")

DASHBOARD_FILE = Path(__file__).resolve().parent.parent / "memory" / "dashboard.json"

# Apps used on this many distinct days become part of the daily dashboard.
PROMOTE_DAYS = 3
# Only consider days within this window when promoting (rolling usage).
PROMOTE_WINDOW_DAYS = 14
# Never auto-add these (system managers, settings, browser-internal pages).
_IGNORE_APPS = {
    "settings", "gnome-control-center", "file explorer", "explorer",
    "task manager", "terminal", "calculator", "chrome", "google-chrome",
    "firefox", "microsoft-edge",
}


def _read() -> dict:
    try:
        if DASHBOARD_FILE.exists():
            data = json.loads(DASHBOARD_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.debug("dashboard read error: %s", e)
    return {"apps": [], "usage": {}}


def _write(data: dict) -> None:
    try:
        DASHBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
        DASHBOARD_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8",
        )
    except OSError as e:
        logger.warning("dashboard write error: %s", e)


# ── Public API ───────────────────────────────────────────────────────────

def get_dashboard_apps() -> list[str]:
    return list(_read().get("apps", []))


def add_to_dashboard(app: str, note: str = "") -> str:
    """Add an app to the daily dashboard. Returns a human-readable result."""
    app = _clean(app)
    if not app:
        return "Give me an app name, like 'add chrome to my dashboard'."
    data = _read()
    apps = data.get("apps", [])
    if app in apps:
        return f"{app} is already on your dashboard."
    apps.append(app)
    data["apps"] = apps
    if note:
        data.setdefault("notes", {})[app] = note
    _write(data)
    return f"Added {app} to your daily dashboard."


def remove_from_dashboard(app: str) -> str:
    app = _clean(app)
    if not app:
        return "Tell me which app to remove, like 'remove chrome from my dashboard'."
    data = _read()
    apps = data.get("apps", [])
    if app not in apps:
        return f"{app} is not on your dashboard."
    data["apps"] = [a for a in apps if a != app]
    data.get("notes", {}).pop(app, None)
    _write(data)
    return f"Removed {app} from your dashboard."


def list_dashboard() -> str:
    apps = get_dashboard_apps()
    if not apps:
        return (
            "Your dashboard is empty. Tell me your daily software, e.g. "
            "'my daily software is chrome, vscode and whatsapp', or just "
            "keep opening apps — I learn automatically."
        )
    return "Your daily dashboard: " + ", ".join(apps) + "."


def open_dashboard(parameters=None, response=None, player=None, session_memory=None) -> str:
    """Open every app on the daily dashboard, in order."""
    apps = get_dashboard_apps()
    if not apps:
        return list_dashboard()

    opened: list[str] = []
    failed: list[str] = []
    from actions.open_app import open_app

    for app in apps:
        try:
            r = open_app(parameters={"app_name": app}, response=response,
                         player=player, session_memory=session_memory) or ""
            if isinstance(r, str) and ("Could not" in r or "Failed" in r or "Unsupported" in r):
                failed.append(app)
            else:
                opened.append(app)
        except Exception as e:
            logger.debug("dashboard open %s failed: %s", app, e)
            failed.append(app)

    parts = []
    if opened:
        parts.append(f"Opened {', '.join(opened)}.")
    if failed:
        parts.append(f"Could not open {', '.join(failed)}.")
    return " ".join(parts) or "Dashboard is empty."


# ── Auto-learning ────────────────────────────────────────────────────────

def log_usage(app: str) -> None:
    """Record that an app was opened today; promote it if used enough.

    Called by ``open_app`` after a successful launch so the dashboard
    learns the user's daily software on its own.
    """
    app = _clean(app)
    if not app or app.lower() in _IGNORE_APPS:
        return
    today = date.today().isoformat()
    data = _read()
    usage = data.setdefault("usage", {})
    days = usage.get(app, [])
    if today not in days:
        days.append(today)
        # Keep only the recent window
        cutoff = _days_ago(PROMOTE_WINDOW_DAYS)
        days[:] = [d for d in days if d >= cutoff]
        usage[app] = days
    apps = data.setdefault("apps", [])
    if app not in apps and len(days) >= PROMOTE_DAYS:
        apps.append(app)
        logger.info("dashboard: auto-promoted '%s' (%d days)", app, len(days))
    _write(data)


def learn_daily_software() -> str:
    """Manually scan usage history and promote apps that qualify."""
    data = _read()
    apps = data.setdefault("apps", [])
    usage = data.get("usage", {})
    promoted = [a for a, days in usage.items()
                if a not in apps and len(days) >= PROMOTE_DAYS]
    for app in promoted:
        apps.append(app)
    if promoted:
        _write(data)
        return "Learned your daily software: " + ", ".join(promoted) + "."
    return "No new daily software found yet — keep opening your apps and I'll learn."


def _clean(app: str) -> str:
    import re
    return re.sub(r"\s+", " ", app.strip().lower()).strip()


def _days_ago(n: int) -> str:
    from datetime import timedelta
    return (date.today() - timedelta(days=n)).isoformat()
