"""get_datetime — returns current date/time. No API calls, zero latency."""

from datetime import datetime


def get_datetime(parameters: dict | None = None, player=None) -> str:
    fmt = (parameters or {}).get("format", "full")

    now = datetime.now()

    if fmt == "day":
        return now.strftime("%A")
    if fmt == "date":
        return now.strftime("%A, %B %d, %Y")
    if fmt == "time":
        return now.strftime("%I:%M %p").lstrip("0")
    if fmt == "unix":
        return str(int(now.timestamp()))

    return now.strftime("%A, %B %d, %Y — %I:%M %p").lstrip("0")
