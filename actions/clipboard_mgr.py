"""Clipboard tools — read the current clipboard and write text into it.

Intents: clipboard_read ("what is in my clipboard", "read my clipboard"),
         clipboard_write ("copy 'hello' to clipboard", "paste this into clipboard")
"""
import logging
import shutil
import subprocess
import sys

logger = logging.getLogger("clipboard")


def _backend():
    """Return (reader, writer) callables using the first available backend."""
    try:
        import pyperclip  # noqa: E402 — optional
        return pyperclip.paste, pyperclip.copy, "pyperclip"
    except ImportError:
        pass
    if sys.platform.startswith("win"):
        def win_read():
            return subprocess.run(["powershell", "-Command", "Get-Clipboard"],
                                  capture_output=True, text=True, timeout=10).stdout
        def win_write(text):
            subprocess.run(["powershell", "-Command", f"Set-Clipboard {text!r}"],
                           capture_output=True, timeout=10)
        return win_read, win_write, "powershell"
    if shutil.which("xclip"):
        def x_read():
            return subprocess.run(["xclip", "-selection", "clipboard", "-o"],
                                  capture_output=True, text=True, timeout=10).stdout
        def x_write(text):
            subprocess.run(["xclip", "-selection", "clipboard"],
                           input=text, text=True, timeout=10)
        return x_read, x_write, "xclip"
    if shutil.which("pbcopy"):
        def mac_read():
            return subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=10).stdout
        def mac_write(text):
            subprocess.run(["pbcopy"], input=text, text=True, timeout=10)
        return mac_read, mac_write, "pbcopy"
    return None, None, None


def clipboard_read(parameters: dict | None = None, player=None) -> str:
    read, _write, _name = _backend()
    if read is None:
        return ("Clipboard access needs pyperclip (pip install pyperclip) or xclip/powershell. "
                "Install one of them then ask me again.")
    try:
        content = read() or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("clipboard read error: %s", exc)
        return f"Could not read clipboard: {exc}"
    if not content.strip():
        return "Your clipboard is empty."
    return f"Clipboard content: {content.strip()[:800]}"


def clipboard_write(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    text = parameters.get("text") or parameters.get("content") or ""
    _read, write, _name = _backend()
    if write is None:
        return ("Clipboard access needs pyperclip (pip install pyperclip) or xclip/powershell. "
                "Install one of them then ask me again.")
    if not text:
        return "Tell me what to copy, for example: 'copy meeting link to clipboard'."
    try:
        write(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("clipboard write error: %s", exc)
        return f"Could not write to clipboard: {exc}"
    return f"Copied to clipboard: {text[:120]}{'…' if len(text) > 120 else ''}"
