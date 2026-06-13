"""Capability Discovery — self-registering plugin system.

Every feature module registers its capabilities here. JARVIS can query
what it can do and the Intent Router uses this to route without LLM.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
import threading
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("capability_registry")

type _Handler = Callable[..., Any]

_REGISTERED: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def register(
    name: str,
    description: str,
    parameters: dict[str, Any] | None = None,
    handler: _Handler | None = None,
    requires_ai: bool = False,
    category: str = "general",
    patterns: list[str] | None = None,
) -> str:
    """Register a capability.

    Args:
        name: Unique dot-separated identifier (e.g. 'spotify.play', 'gmail.send').
        description: Natural language description of what this does.
        parameters: JSON schema dict for parameters (like tool declarations).
        handler: Callable that executes this capability. Must accept **kwargs.
        requires_ai: If True, this capability needs LLM inference (always routed to AI).
        category: Grouping category (e.g. 'communication', 'media', 'system').
        patterns: List of regex patterns to match user intent without LLM.
    """
    with _lock:
        if name in _REGISTERED:
            logger.warning("Capability '%s' already registered — overwriting", name)
        _REGISTERED[name] = {
            "name": name,
            "description": description,
            "parameters": parameters or {},
            "handler": handler,
            "requires_ai": requires_ai,
            "category": category,
            "patterns": patterns or [],
        }
        return f"Registered: {name}"


def get(name: str) -> dict[str, Any] | None:
    with _lock:
        return _REGISTERED.get(name)


def list_capabilities(category: str = "") -> list[dict[str, Any]]:
    with _lock:
        caps = list(_REGISTERED.values())
        if category:
            caps = [c for c in caps if c["category"] == category]
        return [
            {k: v for k, v in c.items() if k != "handler"}
            for c in caps
        ]


def get_categories() -> list[str]:
    with _lock:
        return sorted({c["category"] for c in _REGISTERED.values()})


def unregister(name: str) -> bool:
    with _lock:
        if name in _REGISTERED:
            del _REGISTERED[name]
            return True
        return False


def find_matches(text: str) -> list[dict[str, Any]]:
    """Find capabilities whose patterns match the given text."""
    matches = []
    t_lower = text.lower().strip()
    with _lock:
        for name, cap in _REGISTERED.items():
            if cap["requires_ai"]:
                continue
            for pattern in cap["patterns"]:
                try:
                    if re.search(pattern, t_lower):
                        matches.append(cap)
                        break
                except re.error:
                    continue
    return matches


def get_manifest() -> dict[str, Any]:
    """Full capability manifest as JSON-serializable dict."""
    caps = list_capabilities()
    return {
        "version": "1.0",
        "count": len(caps),
        "categories": get_categories(),
        "capabilities": caps,
    }


def save_manifest(path: str | Path | None = None) -> str:
    """Save the capability manifest to a JSON file."""
    if path is None:
        path = Path(__file__).resolve().parent.parent / "memory" / "capabilities.json"
    data = get_manifest()
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


# ── Registry singleton ───────────────────────────────────────────────────

class CapabilityRegistry:
    def __init__(self):
        self._capabilities: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def register(self, name: str, description: str, **kwargs) -> str:
        return register(name, description, **kwargs)

    def get(self, name: str) -> dict[str, Any] | None:
        return get(name)

    def list(self, category: str = "") -> list[dict[str, Any]]:
        return list_capabilities(category)

    def match(self, text: str) -> list[dict[str, Any]]:
        return find_matches(text)

    def execute(self, name: str, **kwargs) -> Any:
        cap = get(name)
        if not cap:
            raise ValueError(f"Capability '{name}' not found")
        handler = cap.get("handler")
        if not handler:
            raise ValueError(f"Capability '{name}' has no handler")
        return handler(**kwargs)
