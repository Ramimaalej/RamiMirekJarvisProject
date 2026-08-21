"""System-prompt loading & building."""
from __future__ import annotations
import os
import json
from pathlib import Path
from datetime import datetime
import re
import logging

from memory.memory_manager import load_memory, format_memory_for_prompt
from memory.vector_memory  import get_relevant_context, get_memory_count
from skills.skill_loader   import get_active_skill_context
from agent.agent_manager   import get_agent_manager

# Paths
BASE_DIR        = Path(__file__).resolve().parent.parent
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
_SYSTEM_PROMPT_CACHE: str | None = None

# ── Cached time-context: re-built at most once per minute ────────────
_time_ctx_cache:      str   = ""
_time_ctx_cache_min:  int   = -1

def _load_system_prompt() -> str:
    global _SYSTEM_PROMPT_CACHE
    if _SYSTEM_PROMPT_CACHE is not None:
        return _SYSTEM_PROMPT_CACHE
    try:
        _SYSTEM_PROMPT_CACHE = PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        _SYSTEM_PROMPT_CACHE = (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and helpful. You support both executing computer tasks via tools "
            "and engaging in general friendly chat / conversation. Keep responses under 3 sentences."
        )
    return _SYSTEM_PROMPT_CACHE


# ---------------------------------------------------------------------------

def _build_system_prompt(self, user_text: str = "") -> str:
    # ── ORDER MATTERS for Ollama KV prefix caching ─────────────────────
    # Ollama caches the KV attention state of any stable prompt prefix.
    # By putting the STATIC JARVIS protocol text FIRST, Ollama reuses its
    # cached KV for all those tokens on every request.  Only the small
    # dynamic tail (memory + time, ~50-80 tokens) needs re-evaluation.
    # This turns a 17-second first-token into a sub-second one after warmup.
    #
    # Rule: static content first → semi-static memory middle → dynamic time LAST.
    sys_p   = _load_system_prompt()               # cached in-process after first call
    # ── User profile: static enough to sit right after the protocol ─────
    try:
        from core.jarvis_profile import profile_for_prompt  # noqa: E402
        _user_profile_ctx = profile_for_prompt()
    except Exception:
        _user_profile_ctx = ""
    memory  = load_memory()
    mem_str = format_memory_for_prompt(memory)    # semi-static
    now     = datetime.now()
    # ── Human-like recall: recent episodes + past conversations ────────
    # In addition to explicit facts, JARVIS now recalls:
    #   • what was discussed recently (working memory / episodes)
    #   • past conversations that match the current topic
    # This is the "remembers like a real person" layer.
    _episodic_ctx = ""
    try:
        from core.jarvis_memory import format_episode_recall, format_human_recall  # noqa: E402
        _episodic_ctx = format_human_recall(user_text)
    except Exception:
        pass

    # ── Time context: cached per-minute (avoids regenerating tokens) ───
    global _time_ctx_cache, _time_ctx_cache_min
    cur_min = now.hour * 60 + now.minute
    if cur_min != _time_ctx_cache_min:
        _time_ctx_cache = (
            f"[CRITICAL: CURRENT DATE & TIME]\n"
            f"The current year is {now.year}. Today is: {now.strftime('%A, %B %d, %Y')}\n"
            f"Current time: {now.strftime('%I:%M %p')}\n"
            f"IMPORTANT: Ignore any internal training data suggesting a previous year. It is {now.year}."
        )
        _time_ctx_cache_min = cur_min
    time_ctx = _time_ctx_cache

    # ── Vector memory + skills: use pre-fetched result if available ─────
    vec_context   = getattr(self, "_prefetched_vec",   None)
    skill_context = getattr(self, "_prefetched_skill", None)

    if vec_context is None and user_text:
        vec_context = get_relevant_context(user_text)
    if isinstance(vec_context, str) and vec_context:
        vec_count   = get_memory_count()
        vec_context = f"[SEMANTIC MEMORY — {vec_count} stored memories]\n{vec_context}"
    else:
        vec_context = ""

    if skill_context is None and user_text:
        skill_context = get_active_skill_context(user_text)
    if isinstance(skill_context, str) and skill_context:
        skill_context = f"[ACTIVE SKILL]\n{skill_context}"
    else:
        skill_context = ""

    # Background agents status
    agent_mgr  = get_agent_manager()
    running    = agent_mgr.get_running_count()
    agent_info = f"[BACKGROUND AGENTS: {running} running]" if running > 0 else ""

    parts = [sys_p]
    if _user_profile_ctx:
        parts.append(_user_profile_ctx)
    if mem_str:
        parts.append(mem_str)
    if _episodic_ctx:
        parts.append(_episodic_ctx)
    if vec_context:
        parts.append(vec_context)
    if skill_context:
        parts.append(skill_context)
    if agent_info:
        parts.append(agent_info)
    parts.append(time_ctx)
    return "\n\n".join(parts)

