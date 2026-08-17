"""Human-like memory for JARVIS.

Adds a layered memory system on top of the existing long-term / vector
memory, so JARVIS remembers like a real person:

  1. Episodic  — every conversation turn is logged with context
                 ("what happened, when, with whom").
  2. Semantic  — facts, preferences, identity, projects (existing
                 long_term.json, now enriched with timestamps + recency).
  3. Reflective — at the end of a conversation JARVIS extracts durable
                 facts and preferences and consolidates them into long-term
                 storage (like a person reviewing their day).
  4. Recall    — on every new user message, the system automatically
                 retrieves the most relevant past context (vector +
                 recency + explicit memories) and injects it in the prompt.

This module is the recall side; storage is shared with
memory/memory_manager.py and memory/vector_memory.py (no duplicate state).
"""
from __future__ import annotations

import json
import logging
import time as _time
from datetime import datetime
from pathlib import Path
from threading import RLock

logger = logging.getLogger("jarvis.memory")

BASE_DIR    = Path(__file__).resolve().parent.parent
MEMORY_DIR  = BASE_DIR / "memory"
EPISODES_PATH = MEMORY_DIR / "episodes.json"
_lock       = RLock()  # module-level guard (reentrant)

# ── In-memory episode cache (avoid disk reads on every turn) ────────────
_EPISODES:        list[dict] = []
_EPISODES_LOADED: bool       = False


def _load_episodes() -> list[dict]:
    global _EPISODES, _EPISODES_LOADED
    if _EPISODES_LOADED:
        return _EPISODES
    with _lock:
        if EPISODES_PATH.exists():
            try:
                _EPISODES = json.loads(EPISODES_PATH.read_text(encoding="utf-8"))
                if not isinstance(_EPISODES, list):
                    _EPISODES = []
            except Exception:
                _EPISODES = []
        _EPISODES_LOADED = True
        return _EPISODES


def _save_episodes() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    EPISODES_PATH.write_text(
        json.dumps(_EPISODES[-1500:], ensure_ascii=False),   # rolling window
        encoding="utf-8",
    )


def record_episode(user_text: str, assistant_text: str,
                   mode: str = "conversation") -> None:
    """Log one conversation turn — JARVIS episodic memory."""
    episode = {
        "t":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ts": _time.time(),
        "u":  user_text[:500],
        "a":  assistant_text[:1200],
        "m":  mode,
    }
    with _lock:
        _load_episodes()
        _EPISODES.append(episode)
        _save_episodes()


def recent_episodes(n: int = 5) -> list[dict]:
    return _load_episodes()[-n:]


def update_last_episode(assistant_text: str) -> None:
    """Fill in the assistant answer of the most recent recorded episode."""
    with _lock:
        eps = _load_episodes()
        if eps:
            eps[-1]["a"] = assistant_text[:1200]
            _save_episodes()


def format_episode_recall(query: str, top_k: int = 4) -> str:
    """Recency-based recall: the latest relevant episodes.

    Unlike semantic search (embeddings), this mimics "what happened
    recently" — human short-term memory.
    """
    eps = _load_episodes()
    if not eps:
        return ""
    q = query.lower()
    # simple keyword overlap + recency weighting
    scored: list[tuple[float, dict]] = []
    for ep in eps[-300:]:
        if not q:
            score = 0.1
        else:
            words = [w for w in q.split() if len(w) > 2]
            hit = sum(1 for w in words if w in ep["u"].lower() or w in ep["a"].lower())
            if hit == 0:
                continue
            score = hit / max(len(words), 1)
        scored.append((score, ep))
    scored.sort(key=lambda t: -t[0])
    picks = scored[:top_k]
    if not picks:
        picks = [(0.1, e) for e in eps[-2:]]
    lines = []
    for _, ep in picks:
        lines.append(f"- [{ep['t']}] You: {ep['u']}\n  Me:  {ep['a'][:220]}")
    return "\n".join(lines)


def format_human_recall(query: str, top_k: int = 5) -> str:
    """Combined human-style recall for the system prompt.

    Merges: explicit memories (long_term.json), semantic vectors,
    and recent episodes.  Cached per-minute like the time context.
    """
    from memory.memory_manager import load_memory, format_memory_for_prompt
    from memory.vector_memory  import get_relevant_context, search_conversation

    parts: list[str] = []

    # 1. Explicit memory (facts / preferences / identity)
    mem = load_memory()
    mem_str = format_memory_for_prompt(mem)
    if mem_str:
        parts.append(mem_str)

    # 2. Semantic vectors (long-term associations)
    if query:
        vec = get_relevant_context(query, top_k=top_k)
        if isinstance(vec, str) and vec.strip():
            parts.append(f"[SEMANTIC MEMORY]\n{vec}")
        # 3. Past conversations that match
        conv = search_conversation(query, top_k=2)
        if conv:
            lines = []
            for c in conv[:2]:
                lines.append(
                    f"- [{c.get('timestamp', '')[:16]}] "
                    f"You: {str(c.get('user', ''))[:140]}\n"
                    f"  Jarvis: {str(c.get('assistant', ''))[:200]}"
                )
            parts.append("[PAST CONVERSATIONS]\n" + "\n".join(lines))

    # 4. Recent episodes (short-term / working memory)
    rec = format_episode_recall(query, top_k=2)
    if rec:
        parts.append(f"[RECENT EPISODES]\n{rec}")

    return "\n\n".join(parts)
