"""Ultra-fast general-knowledge answers.

For everyday factual questions ("Who won the Nobel Prize?",
"What is the capital of Tunisia?", ...) JARVIS skips the full
tool-calling pipeline and answers directly with the configured
AI model, WITHOUT tool definitions (no function schema = much
faster) and with a tiny temperature-0 prompt.

How it works:
  1. A cheap rule-based classifier decides if the message is a
     general-knowledge question (no tools needed).
  2. `ask_general()` streams a direct answer and returns the
     full text as soon as the first complete sentence arrives.
  3. If the fast path fails for any reason, the caller falls
     back to the normal tool-calling pipeline.

Local Ollama answers arrive sub-second once the model is warm;
cloud providers (Groq, NIM…) answer in a few hundred ms.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("jarvis.general")

# Question starters that almost never need tools
_GENERAL_PREFIXES = (
    "who ", "what ", "when ", "where ", "why ", "how ", "which ",
    "is ", "are ", "was ", "were ", "did ", "does ", "do ",
    "name ", "define ", "explain ", "tell me ", "what's ", "who's ",
)

# Explicit task intents that are NOT general knowledge
_TASK_WORDS = (
    "open", "launch", "start", "run", "send", "text", "whatsapp",
    "telegram", "remind", "timer", "schedule", "shutdown", "restart",
    "set ", "mute", "volume", "brightness", "play", "stop", "download",
    "search ", "find", "weather",
)

_FAST_SYSTEM = (
    "You are JARVIS. Answer the user's general-knowledge question directly, "
    "concisely and accurately in at most 2 sentences. Do not ask questions. "
    "If unsure, say so briefly."
)


def is_general_question(text: str) -> bool:
    """Cheap classifier: general-knowledge question vs. action intent."""
    t = text.strip().lower()
    if not t or len(t) > 220:          # long texts usually contain tasks
        return False
    tspace = f" {t} "
    if any(t.startswith(w) or w in tspace for w in _TASK_WORDS):
        return False
    for w in _GENERAL_PREFIXES:
        if t.startswith(w):
            return True
    if t.endswith("?"):
        return True
    return False


def ask_general(question: str) -> str | None:
    """Get a fast direct answer from the configured AI provider.

    Returns the full answer text, or None if the fast path failed.
    Uses the configured provider/model WITHOUT tool definitions
    (fastest possible path through the existing LLM client).
    """
    try:
        from core.llm_client import call_llm  # noqa: E402

        messages = [
            {"role": "system", "content": _FAST_SYSTEM},
            {"role": "user",   "content": question},
        ]
        result = call_llm(messages, tools=None, timeout=30)
        answer = ""
        if isinstance(result, dict):
            answer = result.get("content", "") or ""
        elif isinstance(result, str):
            answer = result
        answer = answer.strip()
        # cut after the first two sentences — we want it FAST
        if len(answer) > 320:
            answer = answer[:320].rsplit(".", 1)[0] + "."
        return answer or None
    except Exception as e:
        logger.warning("Fast general answer failed: %s", e)
        return None
