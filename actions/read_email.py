import json
import subprocess
import platform
import time
from pathlib import Path


_BASE = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _BASE / "config" / "api_keys.json"

_SYSTEM = platform.system()


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _open_url(url: str) -> bool:
    try:
        if _SYSTEM == "Linux":
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif _SYSTEM == "Darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["start", url])
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[email] URL open failed: {e}")
        return False


def read_email(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    provider = (params.get("provider") or "gmail").lower().strip()

    # Check if IMAP credentials are configured
    cfg = _load_config()
    email_user = cfg.get("email_user", "")
    email_pass = cfg.get("email_pass", "")

    if email_user and email_pass:
        try:
            import imaplib
            import email as email_parser
            from email.header import decode_header

            servers = {
                "gmail":   "imap.gmail.com",
                "outlook": "outlook.office365.com",
                "yahoo":   "imap.mail.yahoo.com",
            }
            server = servers.get(provider, "imap.gmail.com")
            mail = imaplib.IMAP4_SSL(server)
            mail.login(email_user, email_pass)
            mail.select("INBOX")
            status, data = mail.search(None, "ALL")
            if status != "OK":
                return "Could not search inbox."

            ids = data[0].split()[-5:]
            if not ids:
                return "No emails found."

            results = []
            for eid in reversed(ids):
                status, msg_data = mail.fetch(eid, "(RFC822)")
                if status != "OK":
                    continue
                raw = email_parser.message_from_bytes(msg_data[0][1])
                subject_raw = raw.get("Subject", "(no subject)")
                from_raw = raw.get("From", "(unknown)")
                if isinstance(subject_raw, bytes):
                    subject_raw = subject_raw.decode("utf-8", errors="replace")
                decoded, encoding = decode_header(subject_raw)[0]
                if isinstance(decoded, bytes):
                    decoded = decoded.decode(encoding or "utf-8", errors="replace")
                results.append(f"From: {from_raw} | Subject: {decoded}")

            mail.logout()
            if player:
                player.write_log(f"[email] Fetched {len(results)} emails via IMAP")
            summary = " | ".join(results)
            if not summary:
                return "No readable emails found."
            return f"Your latest {len(results)} emails:\n{summary}"

        except Exception as e:
            print(f"[email] IMAP error: {e}")
            return f"Email fetch failed: {e}"

    # No IMAP credentials — open in default browser
    urls = {
        "gmail":   "https://mail.google.com",
        "outlook": "https://outlook.live.com",
        "yahoo":   "https://mail.yahoo.com",
        "proton":  "https://mail.proton.me",
    }
    url = urls.get(provider, "https://mail.google.com")
    if _open_url(url):
        if player:
            player.write_log(f"[email] Opened {provider} in default browser")
        return f"Opened {provider.title()} in your browser."

    return f"Could not open {provider}."
