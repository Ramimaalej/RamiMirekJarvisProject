"""
Google Workspace integration with OAuth for Gmail, Calendar, Drive, Docs, Sheets.
Click "Sign in with Google" in Connections → browser OAuth → JARVIS can use all APIs.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
 
logger = logging.getLogger("google_workspace")

GOOGLE_DIR = Path(__file__).resolve().parent.parent / "gws"
TOKEN_PATH = GOOGLE_DIR / "token.json"
CREDENTIALS_PATH = GOOGLE_DIR / "credentials.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
]

_creds = None
_auth_status_listeners: list[callable] = []


def _get_credentials_path() -> Path:
    return CREDENTIALS_PATH


def _get_token_path() -> Path:
    return TOKEN_PATH


def on_auth_change(callback: callable) -> None:
    _auth_status_listeners.append(callback)


def _notify_listeners() -> None:
    status = is_authenticated()
    for cb in _auth_status_listeners:
        try:
            cb(status)
        except Exception as e:
            logger.warning(f"Auth listener error: {e}")


def is_authenticated() -> bool:
    if _creds and _creds.valid:
        return True
    if _creds and _creds.expired and _creds.refresh_token:
        try:
            from google.auth.transport.requests import Request
            _creds.refresh(Request())
            _save_token(_creds)
            return True
        except Exception:
            return False
    return _load_token() is not None


def _load_token():
    global _creds
    if _creds:
        return _creds
    if TOKEN_PATH.exists():
        try:
            with open(TOKEN_PATH, "r") as f:
                _creds = Credentials.from_json(f.read())
            return _creds
        except Exception as e:
            logger.warning(f"Failed to load token: {e}")
    return None


def _save_token(creds) -> None:
    global _creds
    _creds = creds
    GOOGLE_DIR.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    _notify_listeners()


def has_credentials_json() -> bool:
    return CREDENTIALS_PATH.exists()


def save_credentials_json(client_id: str, client_secret: str) -> None:
    data = {
        "installed": {
            "client_id": client_id.strip(),
            "client_secret": client_secret.strip(),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost"],
        }
    }
    GOOGLE_DIR.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_PATH.write_text(json.dumps(data, indent=2))
    _notify_listeners()


def start_oauth_flow(on_result: callable = None) -> None:
    """Opens browser for Google OAuth consent. Runs in a thread."""
    def _do_auth():
        try:
            if not CREDENTIALS_PATH.exists():
                if on_result:
                    on_result(False, "No credentials.json. Add Client ID/Secret first.")
                return

            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)
            _save_token(creds)
            if on_result:
                on_result(True, "Authenticated! JARVIS can now access Google services.")
        except Exception as e:
            logger.exception("OAuth failed")
            if on_result:
                on_result(False, f"OAuth failed: {e}")

    threading.Thread(target=_do_auth, daemon=True).start()


def revoke_auth() -> None:
    global _creds
    if _creds:
        try:
            from google.auth.transport.requests import Request
            _creds.revoke(Request())
        except Exception:
            pass
    _creds = None
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
    _notify_listeners()


def _get_service(service_name: str, version: str):
    _load_token()
    if not _creds or not _creds.valid:
        if _creds and _creds.expired and _creds.refresh_token:
            from google.auth.transport.requests import Request
            _creds.refresh(Request())
            _save_token(_creds)
        else:
            raise PermissionError("Not authenticated. Sign in with Google first.")
    from googleapiclient.discovery import build
    return build(service_name, version, credentials=_creds)


# ── Gmail ─────────────────────────────────────────────────────────────────


def get_unread_emails(limit: int = 10) -> list[dict]:
    service = _get_service("gmail", "v1")
    results = service.users().messages().list(userId="me", maxResults=limit, q="is:unread").execute()
    messages = []
    for msg in results.get("messages", []):
        full = service.users().messages().get(userId="me", id=msg["id"], format="metadata",
                                              metadataHeaders=["From", "Subject", "Date"]).execute()
        headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
        messages.append({
            "id": msg["id"],
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "snippet": full.get("snippet", ""),
        })
    return messages


def send_email(to: str, subject: str, body: str) -> dict:
    from email.mime.text import MIMEText
    import base64
    service = _get_service("gmail", "v1")
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"id": result.get("id")}


# ── Calendar ──────────────────────────────────────────────────────────────


def get_events(max_results: int = 10, days: int = 7) -> list[dict]:
    service = _get_service("calendar", "v3")
    now = datetime.utcnow()
    end = now + timedelta(days=days)
    events = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat() + "Z",
        timeMax=end.isoformat() + "Z",
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    result = []
    for event in events.get("items", []):
        start = event["start"].get("dateTime", event["start"].get("date", ""))
        result.append({
            "id": event.get("id"),
            "summary": event.get("summary", ""),
            "start": start,
            "end": event["end"].get("dateTime", event["end"].get("date", "")),
            "location": event.get("location", ""),
        })
    return result


def create_event(summary: str, start_time: str, end_time: str, description: str = "",
                 location: str = "") -> dict:
    service = _get_service("calendar", "v3")
    event = {
        "summary": summary,
        "start": {"dateTime": start_time, "timeZone": "UTC"},
        "end": {"dateTime": end_time, "timeZone": "UTC"},
    }
    if description:
        event["description"] = description
    if location:
        event["location"] = location
    result = service.events().insert(calendarId="primary", body=event).execute()
    return {"id": result.get("id"), "link": result.get("htmlLink")}


# ── Drive ─────────────────────────────────────────────────────────────────


def _escape_drive_query(query: str) -> str:
    """Escape single quotes and backslashes for Drive API query syntax."""
    return query.replace("\\", "\\\\").replace("'", "\\'")


def search_drive(query: str, max_results: int = 10) -> list[dict]:
    service = _get_service("drive", "v3")
    safe_q = _escape_drive_query(query)
    results = service.files().list(
        q=f"name contains '{safe_q}'",
        pageSize=max_results,
        fields="files(id, name, mimeType, size, webViewLink)",
    ).execute()
    return [
        {
            "id": f.get("id"),
            "name": f.get("name"),
            "type": f.get("mimeType"),
            "size": f.get("size"),
            "link": f.get("webViewLink"),
        }
        for f in results.get("files", [])
    ]


def upload_drive(file_path: str, mime_type: str = None) -> dict:
    from googleapiclient.http import MediaFileUpload
    service = _get_service("drive", "v3")
    name = Path(file_path).name
    if not mime_type:
        import mimetypes
        mime_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
    result = service.files().create(body={"name": name}, media_body=media).execute()
    return {"id": result.get("id"), "name": result.get("name")}


# ── Docs ──────────────────────────────────────────────────────────────────


def create_doc(title: str, body: str = "") -> dict:
    service = _get_service("docs", "v1")
    doc = service.documents().create(body={"title": title}).execute()
    if body:
        requests = [{"insertText": {"location": {"index": 1}, "text": body}}]
        service.documents().batchUpdate(documentId=doc["documentId"], body={"requests": requests}).execute()
    return {"id": doc.get("documentId"), "link": f"https://docs.google.com/document/d/{doc['documentId']}"}


# ── Sheets ────────────────────────────────────────────────────────────────


def create_sheet(title: str, headers: list[str] = None) -> dict:
    service = _get_service("sheets", "v4")
    spreadsheet = service.spreadsheets().create(body={"properties": {"title": title}}).execute()
    sheet_id = spreadsheet["spreadsheetId"]
    if headers:
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="A1",
            valueInputOption="RAW",
            body={"values": [headers]},
        ).execute()
    return {"id": sheet_id, "link": spreadsheet.get("spreadsheetUrl")}


# ── Tool handler ──────────────────────────────────────────────────────────


def google_workspace_action(parameters: dict, player=None) -> str:
    action = parameters.get("action", "")
    try:
        if action == "check_auth":
            return "Authenticated." if is_authenticated() else "Not authenticated."

        if action == "gmail_unread":
            limit = int(parameters.get("limit", 10))
            emails = get_unread_emails(limit)
            if not emails:
                return "No unread emails."
            lines = [f"{e['from']}: {e['subject']}" for e in emails]
            return f"You have {len(emails)} unread emails:\n" + "\n".join(lines[:5])

        elif action == "gmail_send":
            return send_email(parameters["to"], parameters["subject"], parameters["body"]).get("id", "sent")

        elif action == "calendar_events":
            days = int(parameters.get("days", 7))
            events = get_events(days=days)
            if not events:
                return "No upcoming events."
            lines = [f"{e['start'][:10]} {e['summary']}" for e in events]
            return f"Upcoming events:\n" + "\n".join(lines)

        elif action == "calendar_create":
            r = create_event(parameters["summary"], parameters["start_time"], parameters["end_time"])
            return f"Event created: {r.get('link', '')}"

        elif action == "drive_search":
            files = search_drive(parameters.get("query", ""))
            if not files:
                return "No files found."
            return "\n".join(f"{f['name']} ({f.get('type', '')})" for f in files)

        elif action == "docs_create":
            r = create_doc(parameters.get("title", "Untitled"), parameters.get("body", ""))
            return f"Doc created: {r.get('link', '')}"

        elif action == "sheets_create":
            r = create_sheet(parameters.get("title", "Untitled"), parameters.get("headers"))
            return f"Sheet created: {r.get('link', '')}"

        else:
            return f"Unknown Google action: {action}"
    except PermissionError:
        return "Google not authenticated. Open Connections → Google Workspace and sign in."
    except Exception as e:
        logger.exception(f"Google action failed: {action}")
        return f"Google {action} failed: {e}"
