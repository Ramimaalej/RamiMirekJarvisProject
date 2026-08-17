"""Fast Browser action — ultra-fast browser automation for MARK XL.

Exposes the core.fast_browser singleton as a capability registered in the
intent router, so commands like "open youtube", "go to gmail", "click login",
"scroll down" are executed in milliseconds by attaching directly to the
user's already-running browser (CDP) — no browser startup, no session loss.
"""
from __future__ import annotations

import re


def fast_browser(parameters: dict | None = None) -> str:
    """Execute a fast browser command from a plain-text instruction."""
    parameters = parameters or {}
    text = (parameters.get("text") or parameters.get("command") or "").strip()
    if not text:
        return "No browser command given."

    from core.fast_browser import get_fast_browser
    fb = get_fast_browser()
    return fb.run(text)


# ---------------------------------------------------------------------------
# Capability registration metadata
# ---------------------------------------------------------------------------
CAPABILITY = {
    "name":        "fast_browser",
    "subsystem":   "browser",
    "description": "Ultra-fast browser automation — open pages, click, type, "
                   "scroll, grab text. Attaches to your running browser via CDP.",
    "patterns": [
        r"^(open|go to|visit|navigate to)\s+.+",
        r"^click\s+.+",
        r"^type\s+.*\s+into\s+.+",
        r"^scroll\s+(up|down)(\s+\d+)?",
        r"^(refresh|reload|back|new tab|close tab)",
        r"^(what'?s (on|in) (the )?page|read (the )?page|grab (the )?page)",
        r"^screenshot",
    ],
    "handler":     "fast_browser",
    "params":      {},
    "requires_ai": False,
}


def register(registry):
    """Register into a CapabilityRegistry-style registry."""
    registry.add(CAPABILITY)
