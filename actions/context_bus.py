import json
import logging
import threading
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable

logger = logging.getLogger("context_bus")


class ContextBus:
    """Publish/subscribe context bus.

    Every subsystem can publish context (e.g. "current_app", "meeting_status",
    "battery_level"). Any subscriber can receive real-time updates.

    This is what makes JARVIS feel like it knows what's happening.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._context: dict[str, Any] = {}
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._history: list[dict] = []
        self._max_history = 100

    def publish(self, key: str, value: Any, source: str = ""):
        with self._lock:
            old = self._context.get(key)
            self._context[key] = value
            entry = {
                "key": key,
                "value": value,
                "old": old,
                "source": source,
                "timestamp": datetime.now().isoformat(),
            }
            self._history.append(entry)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

            subscribers = list(self._subscribers.get(key, []))
            all_subscribers = list(self._subscribers.get("*", []))

        for cb in subscribers + all_subscribers:
            try:
                cb(key, value, old, source)
            except Exception as e:
                logger.warning("Context subscriber error: %s", e)

    def subscribe(self, key: str, callback: Callable):
        with self._lock:
            self._subscribers[key].append(callback)

    def unsubscribe(self, key: str, callback: Callable):
        with self._lock:
            if callback in self._subscribers[key]:
                self._subscribers[key].remove(callback)

    def get(self, key: str, default: Any = None) -> Any:
        return self._context.get(key, default)

    def get_all(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._context)

    def get_history(self, key: str = "", limit: int = 20) -> list[dict]:
        with self._lock:
            if key:
                entries = [e for e in self._history if e["key"] == key]
            else:
                entries = list(self._history)
            return entries[-limit:]

    def search(self, query: str) -> list[dict]:
        q = query.lower()
        with self._lock:
            return [
                e for e in self._history
                if q in str(e["key"]).lower() or q in str(e["value"]).lower()
            ]

    def clear(self):
        with self._lock:
            self._context.clear()
            self._history.clear()

    def get_summary(self) -> str:
        ctx = self.get_all()
        if not ctx:
            return "No context data."
        lines = [f"Context snapshot ({len(ctx)} keys):"]
        for k, v in sorted(ctx.items()):
            lines.append(f"  {k} = {v}")
        return "\n".join(lines)


# ── Singleton ───────────────────────────────────────────────────────────

_bus: ContextBus | None = None
_lock = threading.Lock()


def get_bus() -> ContextBus:
    global _bus
    if _bus is None:
        with _lock:
            if _bus is None:
                _bus = ContextBus()
    return _bus


# ── Convenience ─────────────────────────────────────────────────────────

def publish(key: str, value: Any, source: str = ""):
    get_bus().publish(key, value, source)


def subscribe(key: str, callback: Callable):
    get_bus().subscribe(key, callback)


def get_context(key: str, default: Any = None) -> Any:
    return get_bus().get(key, default)


def get_all_context() -> dict[str, Any]:
    return get_bus().get_all()
