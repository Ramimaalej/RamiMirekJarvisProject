"""Screen Vision action — Jarvis looks at your screen and reads the text on it.

Triggered by the intent "screen_vision" (see actions/intent_router.py),
usually from commands like:
  "see my screen" / "what's on my screen" / "read the text" /
  "lis l'écran" / "dis-moi ce qu'il y a à l'écran"
"""
from __future__ import annotations

from core.jarvis_vision import see_screen, format_screen_summary


def screen_vision(params: dict | None = None) -> str:
    """Capture the screen, OCR it, and return the text summary."""
    lang = "fra" if (params or {}).get("lang", "eng") == "fra" else "eng"
    data = see_screen(lang)
    return format_screen_summary(data)
