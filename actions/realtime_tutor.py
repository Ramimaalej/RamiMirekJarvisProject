from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

_PARENT = Path(__file__).resolve().parent
_BACKEND_DIR = _PARENT / "realtime_tutor" / "backend"
_FRONTEND_DIR = _PARENT / "realtime_tutor" / "frontend" / "out"

_tutor_process: subprocess.Popen | None = None
_tutor_port: int = 8000
_on_stop_callback = None


def _find_free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_server(port: int, timeout: float = 10.0) -> bool:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.3)
    return False


def realtime_tutor(
    parameters: dict | None = None,
    response: callable = None,
    player=None,
    session_memory: dict | None = None,
) -> str:
    global _tutor_process, _tutor_port, _on_stop_callback

    if _tutor_process is not None:
        return "Gemini Tutor is already running."

    player = player

    # Check frontend build
    if not (_FRONTEND_DIR / "index.html").exists():
        return "Frontend not built. Run: cd actions/realtime_tutor/frontend && npm run build"

    # Find free port
    _tutor_port = _find_free_port()

    # Start backend
    backend_script = str(_BACKEND_DIR / "main.py")
    _tutor_process = subprocess.Popen(
        [sys.executable, backend_script, str(_tutor_port)],
        cwd=str(_BACKEND_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if not _wait_for_server(_tutor_port):
        _tutor_process.kill()
        _tutor_process = None
        return "Failed to start Gemini Tutor backend."

    # Open the frontend in the GUI web panel
    url = f"http://127.0.0.1:{_tutor_port}"
    if player and hasattr(player, "open_tutor_panel"):
        player.open_tutor_panel(url)
        _on_stop_callback = getattr(player, "close_tutor_panel", None)
        return f"Gemini Tutor started at {url}"

    # Fallback: open in browser
    import webbrowser
    webbrowser.open(url)
    return f"Gemini Tutor started in your browser at {url}"


def stop_tutor() -> str:
    global _tutor_process, _on_stop_callback

    if _tutor_process is None:
        return "Gemini Tutor is not running."

    _tutor_process.terminate()
    try:
        _tutor_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _tutor_process.kill()

    _tutor_process = None

    if _on_stop_callback:
        try:
            _on_stop_callback()
        except Exception:
            pass
        _on_stop_callback = None

    return "Gemini Tutor stopped."
