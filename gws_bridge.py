import asyncio
import json
import logging
import shlex
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("gws_bridge")

_BASE_DIR = Path(__file__).resolve().parent
_GWS_DIR = _BASE_DIR / "gws"
_CREDENTIALS_PATH = _GWS_DIR / "credentials.json"


class GwsError(Exception):
    def __init__(self, message: str, raw: str = ""):
        self.raw = raw
        super().__init__(message)


def _check_credentials() -> bool:
    return _CREDENTIALS_PATH.exists()


async def _run_gws(*args: str, timeout: int = 30) -> Any:
    cmd = ["gws", *args, "--format", "json"]
    logger.debug(f"Running: {' '.join(shlex.quote(a) for a in cmd)}")
    env = {
        "GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE": str(_CREDENTIALS_PATH),
    }
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**__import__("os").environ, **env},
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise GwsError(f"Command timed out after {timeout}s: {' '.join(cmd)}")
    if proc.returncode != 0:
        err_text = stderr.decode().strip()
        raise GwsError(
            f"gws error (code {proc.returncode}): {err_text[:500]}",
            raw=err_text,
        )
    out = stdout.decode().strip()
    if not out:
        return {}
    return json.loads(out)


# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------

async def get_unread_emails(limit: int = 10) -> list[dict]:
    return await _run_gws("gmail", "+triage", "--max", str(limit))


async def search_emails(query: str) -> list[dict]:
    return await _run_gws("gmail", "+triage", "--query", query)


async def read_email(message_id: str) -> dict:
    return await _run_gws("gmail", "+read", "--id", message_id, "--headers", "--format", "json")


async def send_email(to: str, subject: str, body: str) -> dict:
    return await _run_gws(
        "gmail", "+send",
        "--to", to,
        "--subject", subject,
        "--body", body,
    )


async def reply_email(message_id: str, body: str) -> dict:
    return await _run_gws(
        "gmail", "+reply",
        "--message-id", message_id,
        "--body", body,
    )


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------

async def get_todays_agenda() -> list[dict]:
    result = await _run_gws("calendar", "+agenda", "--today")
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("items", [])
    return []


async def get_upcoming_events(days: int = 7) -> list[dict]:
    result = await _run_gws("calendar", "+agenda", "--days", str(days))
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("items", [])
    return []


async def create_event(
    title: str,
    date: str,
    time: str,
    duration_minutes: int,
    description: str = "",
    meet: bool = False,
) -> dict:
    start_iso = f"{date}T{time}:00"
    start_dt = datetime.fromisoformat(start_iso)
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

    cmd = [
        "calendar", "+insert",
        "--summary", title,
        "--start", start_iso,
        "--end", end_iso,
    ]
    if description:
        cmd.extend(["--description", description])
    if meet:
        cmd.append("--meet")

    return await _run_gws(*cmd)


async def delete_event(event_id: str) -> dict:
    return await _run_gws(
        "calendar", "events", "delete",
        "--params", json.dumps({"calendarId": "primary", "eventId": event_id}),
    )


# ---------------------------------------------------------------------------
# Drive
# ---------------------------------------------------------------------------

async def search_files(query: str) -> list[dict]:
    result = await _run_gws(
        "drive", "files", "list",
        "--params", json.dumps({"q": query, "pageSize": 20}),
    )
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return result.get("files", result.get("items", []))
    return []


async def upload_file(local_path: str, folder_id: str | None = None) -> dict:
    cmd = ["drive", "+upload", local_path]
    if folder_id:
        cmd.extend(["--parent", folder_id])
    return await _run_gws(*cmd)


async def create_doc(title: str, content: str) -> dict:
    doc = await _run_gws(
        "docs", "documents", "create",
        "--json", json.dumps({"title": title}),
    )
    doc_id = doc.get("documentId") or doc.get("id")
    if doc_id and content:
        await _run_gws(
            "docs", "+write",
            "--document", doc_id,
            "--text", content,
        )
    return doc


# ---------------------------------------------------------------------------
# Meet
# ---------------------------------------------------------------------------

async def create_meet(title: str, date: str, time: str, duration_minutes: int = 60) -> dict:
    result = await create_event(
        title=title,
        date=date,
        time=time,
        duration_minutes=duration_minutes,
        meet=True,
    )
    return result


# ---------------------------------------------------------------------------
# Auth check
# ---------------------------------------------------------------------------

async def is_authenticated() -> bool:
    if not _check_credentials():
        return False
    try:
        await _run_gws("calendar", "+agenda", "--today", timeout=10)
        return True
    except GwsError:
        return False
