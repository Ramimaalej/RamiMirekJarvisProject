from __future__ import annotations

import imaplib
import email
from email.policy import default
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

def _decrypt_creds() -> dict:
    key_file = _CONFIG_DIR / ".email_key"
    enc_file = _CONFIG_DIR / "email_creds.enc"
    key = key_file.read_text().strip()
    cipher = Fernet(key.encode())
    data = cipher.decrypt(enc_file.read_bytes())
    return json.loads(data)


def _parse_email(msg) -> dict:
    subject = msg.get("Subject", "(No Subject)")
    sender = msg.get("From", "(Unknown Sender)")
    date = msg.get("Date", "(Unknown Date)")
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_content()
                break
        else:
            for part in msg.walk():
                if part.get_content_type().startswith("text/"):
                    body = part.get_content()
                    break
    else:
        body = msg.get_content()
    if body:
        body = re.sub(r'\s+', ' ', body).strip()
    return {"subject": subject, "sender": sender, "date": date, "body": body or ""}


def _fetch_emails(hours: int = 24, keyword: str | None = None, limit: int = 20) -> list[dict]:
    creds = _decrypt_creds()
    since = (datetime.now() - timedelta(hours=hours)).strftime("%d-%b-%Y")
    last_error = None
    for attempt in range(2):
        conn = None
        try:
            conn = imaplib.IMAP4_SSL(creds["imap_server"], creds["imap_port"])
            conn.login(creds["email"], creds["app_password"])
            conn.select("INBOX")

            # Fetch email IDs with SINCE search
            try:
                if keyword:
                    _, data = conn.search(None, f'SINCE {since} TEXT "{keyword}"')
                else:
                    _, data = conn.search(None, f'SINCE {since}')
            except imaplib.IMAP4.error:
                _, data = conn.search(None, "ALL")

            msg_ids = data[0].split()[-limit*3:] if data[0] else []
            emails = []
            for mid in reversed(msg_ids):
                if len(emails) >= limit:
                    break
                # Fetch both RFC822 content and Gmail labels
                try:
                    _, msg_data = conn.fetch(mid, "(RFC822 X-GM-LABELS)")
                except imaplib.IMAP4.error:
                    _, msg_data = conn.fetch(mid, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue

                # Check if this email has category labels (UPDATES, PROMOTIONS, etc.)
                is_primary = True
                raw_labels = None
                for part in msg_data:
                    if isinstance(part, tuple) and len(part) == 2:
                        raw_labels = part[0]
                    elif isinstance(part, bytes):
                        label_str = part.decode(errors="replace")
                        if "^CATEGORY_" in label_str:
                            for cat in ("UPDATES", "PROMOTIONS", "SOCIAL", "FORUMS"):
                                if f"^CATEGORY_{cat}" in label_str:
                                    is_primary = False
                                    break

                # Parse RFC822
                raw_email = None
                for part in msg_data:
                    if isinstance(part, tuple) and len(part) == 2:
                        raw_email = part[1]
                        break

                if not raw_email:
                    continue

                parsed = _parse_email(email.message_from_bytes(raw_email, policy=default))
                parsed["id"] = mid.decode()

                # Skip non-primary emails
                if not is_primary:
                    continue

                emails.append(parsed)
            return emails
        except (imaplib.IMAP4.error, OSError, Exception) as e:
            last_error = e
            if attempt == 0:
                import time as _t
                _t.sleep(0.5)
                continue
        finally:
            if conn is not None:
                try:
                    conn.logout()
                except Exception:
                    pass
    raise last_error or RuntimeError("Failed to fetch emails")


def read_emails(parameters: dict | None = None, player=None, **kwargs) -> str:
    hours = int(parameters.get("hours", 24)) if parameters else 24
    keyword = parameters.get("keyword") if parameters else None
    limit = int(parameters.get("limit", 10)) if parameters else 10
    try:
        emails = _fetch_emails(hours=hours, keyword=keyword, limit=limit)
    except Exception as e:
        return f"Failed to fetch emails: {e}"
    if not emails:
        return "No emails found."
    lines = [f"You have {len(emails)} email(s):"]
    for i, m in enumerate(emails, 1):
        body = m["body"][:120].replace("\n", " ")
        lines.append(f"{i}. From: {m['sender']} | Subject: {m['subject']} | {body}")
    return "\n".join(lines)
