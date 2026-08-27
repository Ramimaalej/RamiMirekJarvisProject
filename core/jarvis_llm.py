"""LLM turn processing (stream + overlapped TTS)."""
from __future__ import annotations
import traceback
import time
import re
import queue
import logging
import json
import asyncio
import threading
from typing import Any

from memory.vector_memory import get_relevant_context, store_conversation
from skills.skill_loader  import get_active_skill_context
from actions.intent_router import route as route_intent
from core.jarvis_utils   import _is_greeting
from core.tools.declarations import OLLAMA_TOOLS
from core.llm_client     import call_llm_stream

def _load_config() -> dict:
    from memory.config_manager import load_config as _lc
    return _lc()

def _run_async(coro) -> Any:
    """Run an async coroutine synchronously. Safe because this runs in a background thread."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# ------------------------------------------------------------------
# LLM processing loop
# ------------------------------------------------------------------

def _prefetch_context(self, user_text: str) -> None:
    try:
        self._prefetched_vec   = get_relevant_context(user_text)
        self._prefetched_skill = get_active_skill_context(user_text)
    except Exception:
        self._prefetched_vec   = ""
        self._prefetched_skill = ""

# ------------------------------------------------------------------
# Ultra-fast general-knowledge answers
# ------------------------------------------------------------------

def _fast_general_answer(self, user_text: str) -> None:
    """Answer a general-knowledge question directly — no tools, no
    80-tool payload.  This is the fastest possible path: a single
    tiny model request (Ollama local or the fastest configured cloud
    provider) returns the answer in sub-second when warm."""
    try:
        from core.jarvis_general import ask_general  # noqa: E402
        answer = ask_general(user_text)
        if answer:
            self.ui.write_log_instant(f"Jarvis: {answer}")
            self.speak(answer)
            assistant_msg = {"role": "assistant", "content": answer}
            with self._conv_lock:
                self._conversation.append(assistant_msg)
            threading.Thread(target=store_conversation, args=(user_text, answer), daemon=True).start()
            try:
                from core.jarvis_memory import update_last_episode  # noqa: E402
                update_last_episode(answer)
            except Exception:
                pass
            return True
    except Exception as e:
        logger = logging.getLogger("jarvis.general")
        logger.warning("Fast path failed: %s", e)
    return False


def _offline_identity_scope_reply(user_text: str) -> str:
    """Answer a small, safe identity-and-capability baseline without an LLM.

    This protects essential setup and diagnostic prompts from a temporarily
    unavailable model provider.  It deliberately has a narrow trigger and
    never attempts to impersonate a tool result or answer arbitrary requests.
    """
    normalized = " ".join(user_text.casefold().split())
    asks_about_identity = "jarvis mark xl" in normalized and any(
        phrase in normalized
        for phrase in (
            "state your role",
            "your role",
            "real capability",
            "must not claim",
            "capability you must not claim",
        )
    )
    if not asks_about_identity:
        return ""

    return (
        "I am JARVIS MARK XL, Rami Maalej’s desktop AI assistant. "
        "One real capability is routing supported local tools or configured "
        "AI providers and reporting their verified results. I must not claim "
        "that I opened an application, read your screen, accessed private data, "
        "or fetched live information without a confirmed tool result."
    )


def _llm_unavailable_reply(short: str) -> str:
    """Describe a model-provider failure without confusing it with refusal."""
    hint = _llm_error_hint(short)
    if hint:
        return f"I could not reach the configured AI provider. {hint}"
    return (
        "I could not reach the configured AI provider, so I cannot answer "
        "this request yet. Open Settings → PROVIDER, verify the selected "
        "provider and model, then try again."
    )


def _process_message(self, user_text: str) -> None:
    """
    Full turn: user_text → LLM stream → TTS (overlapped) → tool execution

    Streaming TTS: sentence events are piped to the TTS queue AS they
    arrive from the LLM, so Kokoro starts synthesising sentence 1 while
    the LLM is still generating sentence 2.  This cuts perceived latency
    from (LLM_total + TTS_total) down to roughly max(LLM_total, TTS_total).

    Tool-call responses never emit sentence events, so the TTS overlap
    only kicks in for pure conversational replies — which is exactly when
    it matters most.

    Cancellation: snapshots self._generation at entry.  If the counter
    advances (new text command from the UI), this call winds down at the
    next safe checkpoint so the new message can be processed immediately.
    """
    _gen = self._generation
    def _cancelled() -> bool:
        return _gen != self._generation

    # Wait for background prefetch to complete (started in _listen_whisper)
    pf_thread = getattr(self, "_prefetch_thread", None)
    if pf_thread and pf_thread.is_alive():
        pf_thread.join(timeout=2.0)
    # If it didn't finish in time, _build_system_prompt falls through to inline load
    self._prefetch_thread = None

    self._auto_switch_language(user_text)
    self.ui.set_state("THINKING")
    self.ui.write_log(f"You: {user_text}")

    # ── Episodic memory: log every conversation turn ──────────────────
    try:
        from core.jarvis_memory import record_episode  # noqa: E402
        threading.Thread(target=record_episode, args=(user_text, ""), daemon=True).start()
    except Exception:
        pass

    with self._conv_lock:
        self._conversation.append({"role": "user", "content": user_text})

    # Identity/scope diagnostics should remain answerable even while a cloud
    # provider, a local model server, or the network is being repaired.
    offline_reply = _offline_identity_scope_reply(user_text)
    if offline_reply:
        self.ui.write_log_instant(f"Jarvis: {offline_reply}")
        self.speak(offline_reply)
        assistant_msg = {"role": "assistant", "content": offline_reply}
        with self._conv_lock:
            self._conversation.append(assistant_msg)
        threading.Thread(
            target=store_conversation,
            args=(user_text, offline_reply),
            daemon=True,
        ).start()
        try:
            from core.jarvis_memory import update_last_episode  # noqa: E402
            update_last_episode(offline_reply)
        except Exception:
            pass
        if not self.ui.muted:
            self.ui.set_state("LISTENING")
        return

    MAX_HISTORY = 10
    if len(self._conversation) > MAX_HISTORY:
        self._conversation = self._conversation[-MAX_HISTORY:]

    messages = [
        {"role": "system", "content": self._build_system_prompt(user_text)}
    ] + list(self._conversation)

    # ── Intent Router: bypass LLM for common commands ─────────────────
    self._last_intent = route_intent(user_text)
    if self._last_intent.matched and not self._last_intent.requires_ai:
        # Route directly — no LLM call needed
        tool_params = self._last_intent.handler_params
        self.ui.write_log(f"INTENT: {self._last_intent.intent_name} → {tool_params}")
        result = self._execute_tool(self._last_intent.handler_name, tool_params)
        if result == "__SILENT__":
            # Silent tools (save_memory) — don't speak, don't store
            return
        if result:
            self.speak(result)
            self.ui.write_log_instant(f"Jarvis: {result}")
        assistant_msg = {"role": "assistant", "content": result or ""}
        with self._conv_lock:
            self._conversation.append(assistant_msg)
        threading.Thread(target=store_conversation, args=(user_text, result or ""), daemon=True).start()
        try:
            from core.jarvis_memory import update_last_episode  # noqa: E402
            update_last_episode(result or "")
        except Exception:
            pass
        return

    if _cancelled():
        self.ui.write_log("SYS: Cancelled — new input received")
        return

    # ── Ultra-fast general-knowledge path ─────────────────────────────
    # Questions like "Who won the Nobel Prize?" skip the whole
    # tool-calling pipeline and are answered directly by the fastest
    # available model.  On failure we fall through to the normal path.
    try:
        from core.jarvis_general import is_general_question  # noqa: E402
        if is_general_question(user_text):
            if _fast_general_answer(self, user_text):
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                return
    except Exception:
        pass

    # Tools whose output needs a second LLM round to summarise/interpret.
    # Everything else returns a user-ready string → speak directly.
    _NEEDS_LLM_ROUND = {"web_search", "screen_process", "agent_task"}

    # Tools that require clear user intent — never run them for greetings
    _INTENT_TOOLS = {
        "open_app", "computer_control", "computer_settings",
        "send_message", "play_music", "game_updater", "flight_finder",
    }

    MAX_TOOL_ROUNDS = 6
    for _round in range(MAX_TOOL_ROUNDS):
        if _cancelled():
            self.ui.write_log("SYS: Cancelled — new input received")
            break

        final_content    = ""
        final_tool_calls: list = []
        _streamed: list[str] = []

        # Skip sending ~50 tool definitions for simple greetings
        try:
            from core.llm_client import get_llm_provider
            _provider = get_llm_provider()
        except Exception:
            _provider = "ollama"

        # Ollama, Groq, NVIDIA NIM, OpenRouter, and OpenAI-compatible
        # providers all support tool calling — send tools unless it's
        # a greeting on the first round.
        _tools = None
        if not (_round == 0 and _is_greeting(user_text)):
            _tools = OLLAMA_TOOLS

        # ── Apply per-intent model override if configured ──────────
        override = None
        if self._last_intent.matched:
            ov = _load_config().get("model_overrides", {}).get(self._last_intent.intent_name)
            if ov:
                override = (ov.get("provider"), ov.get("model"))
        try:
            for event in call_llm_stream(messages, _tools, model_override=override):
                if event["type"] == "sentence":
                    # ── Overlap TTS with LLM generation ─────────────────
                    # Queue this sentence immediately; the TTS worker
                    # synthesises it while the LLM is still generating
                    # the next one. Write to log at the same time.
                    _streamed.append(event["text"])
                    self.speak(event["text"])
                    if len(_streamed) == 1:
                        self.ui.write_log_instant(f"Jarvis: {event['text']}")
                    else:
                        self.ui.write_log_instant(event["text"])
                elif event["type"] == "done":
                    final_content    = event["content"]
                    final_tool_calls = event["tool_calls"]
        except RuntimeError as e:
            short = str(e)[:120]
            self.ui.write_log(f"ERR: LLM — {short}")
            reply = _llm_unavailable_reply(short)
            self.ui.write_log_instant(f"Jarvis: {reply}")
            self.speak(reply)
            fallback = {"role": "assistant", "content": reply}
            with self._conv_lock:
                self._conversation.append(fallback)
            return

        # ── Greeting guard ────────────────────────────────────────────────
        # Small models hallucinate action tool calls for greetings.
        # Strip ALL tool calls if user just said hello — the prompt already
        # tells the model not to run tools for general chat.
        if final_tool_calls and _round == 0 and _is_greeting(user_text):
            final_tool_calls = []
            if not final_content:
                final_content = "Hello! How can I help you?"

        # ── No tool calls: pure conversational reply ─────────────────────
        if not final_tool_calls:
            if _streamed:
                # Text already written to log during streaming — just update history.
                assistant_msg = {"role": "assistant", "content": final_content}
                messages.append(assistant_msg)
                with self._conv_lock:
                    self._conversation.append(assistant_msg)
            elif final_content:
                # Very short response (no sentence boundary) — speak now.
                assistant_msg = {"role": "assistant", "content": final_content}
                messages.append(assistant_msg)
                with self._conv_lock:
                    self._conversation.append(assistant_msg)
                self.ui.write_log(f"Jarvis: {final_content}")
                self.speak(final_content)
            # Store in vector memory
            if final_content:
                threading.Thread(target=store_conversation, args=(user_text, final_content), daemon=True).start()
            try:
                from core.jarvis_memory import update_last_episode  # noqa: E402
                update_last_episode(final_content or "")
            except Exception:
                pass
            break

        # ── Tool calls present ────────────────────────────────────────────
        assistant_msg = {
            "role":       "assistant",
            "content":    final_content or "",
            "tool_calls": final_tool_calls,
        }
        messages.append(assistant_msg)
        with self._conv_lock:
            self._conversation.append(assistant_msg)

        # ── Fast path: save_memory + verbal content in same round ────────
        _only_memory = all(
            tc.get("function", {}).get("name") == "save_memory"
            for tc in final_tool_calls
        )
        if _only_memory and final_content:
            for tc in final_tool_calls:
                fn    = tc.get("function", {})
                targs = fn.get("arguments", {})
                if isinstance(targs, str):
                    try:
                        targs = json.loads(targs)
                    except Exception:
                        targs = {}
                self._execute_tool("save_memory", targs)
            assistant_msg2 = {"role": "assistant", "content": final_content}
            messages.append(assistant_msg2)
            with self._conv_lock:
                self._conversation.append(assistant_msg2)
            self.ui.write_log(f"Jarvis: {final_content}")
            if not _streamed:
                self.speak(final_content)
            break

        # ── Execute tools ─────────────────────────────────────────────────
        all_silent    = True
        _tool_results: list[tuple[str, str]] = []

        for tc in final_tool_calls:
            fn    = tc.get("function", {})
            tname = fn.get("name", "")
            targs = fn.get("arguments", {})
            if isinstance(targs, str):
                try:
                    targs = json.loads(targs)
                except Exception:
                    targs = {}

            tc_id = tc.get("id", "")
            self.ui.write_log(f"SYS: ▶ {tname}")
            result = self._execute_tool(tname, targs)

            if result != "__SILENT__":
                all_silent = False
                _tool_results.append((tname, result))

            tool_msg: dict = {
                "role":    "tool",
                "content": "Done." if result == "__SILENT__" else str(result),
            }
            if tc_id:
                tool_msg["tool_call_id"] = tc_id

            messages.append(tool_msg)
            with self._conv_lock:
                self._conversation.append(tool_msg)

        if _cancelled():
            self.ui.write_log("SYS: Cancelled after tool execution")
            break

        # ── Fast-ack: every call was save_memory (silent) ────────────────
        # Instead of saying "Noted.", do a real conversational follow-up.
        if all_silent:
            # Continue the loop — model will now reply conversationally
            # since tool results are already appended to messages.
            continue

        # ── Direct-result: speak tool output, skip LLM round ────────────
        if _tool_results and not any(n in _NEEDS_LLM_ROUND for n, _ in _tool_results):
            _, _reply = _tool_results[-1]
            _amsg = {"role": "assistant", "content": _reply}
            messages.append(_amsg)
            with self._conv_lock:
                self._conversation.append(_amsg)
            self.ui.write_log(f"Jarvis: {_reply}")
            self.speak(_reply)
            # Store in vector memory
            threading.Thread(target=store_conversation, args=(user_text, _reply), daemon=True).start()
            try:
                from core.jarvis_memory import update_last_episode  # noqa: E402
                update_last_episode(_reply or "")
            except Exception:
                pass
            break

    if not self.ui.muted:
        self.ui.set_state("LISTENING")

# ------------------------------------------------------------------
# LLM error hints (clear, actionable messages for the user)
# ------------------------------------------------------------------

def _llm_error_hint(short: str) -> str:
    """Return a short, actionable hint for common LLM errors (URL/Auth)."""
    s = short.lower()
    if "localhost:11434" in short or "ollama" in s:
        return "Local model server (Ollama) is not reachable — run: ollama serve"
    if "401" in s or "api key" in s or "unauthorized" in s or "forbidden" in s:
        if "groq" in s:
            return "Groq API key missing/invalid — create a free key at console.groq.com and add it in Settings"
        return "API key missing or invalid — open Settings → PROVIDER and enter your API key"
    if "groq" in s or "openrouter" in s or "nvidia" in s or "openai" in s:
        return f"Cloud provider unreachable — check your API key and internet connection"
    return ""

def hint_short(hint: str) -> str:
    """Return a short spoken version of an error hint."""
    return hint or "I cannot do that."

# ------------------------------------------------------------------
# STT listening loops
# ------------------------------------------------------------------
