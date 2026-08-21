"""JarvisLocal — slim orchestrator.

This is the *only* place where the assistant's life-cycle lives.
Every feature is now a dedicated module in core/ (see imports below).

Extracted from main.py — same behaviour, zero semantic change.
"""
from __future__ import annotations

import logging
import queue
import threading
import traceback
from typing import Any

from ui import JarvisUI

from core.tools.executor    import execute_tool
from core.tools.declarations import OLLAMA_TOOLS
from core.jarvis_config   import reconfigure as do_reconfigure
from core.jarvis_llm      import _process_message as _pm, _run_async as _ra, _prefetch_context as _pc
from core.jarvis_stt      import _listen_whisper as _lw, _listen_vosk as _lv, _text_command_loop as _tcl
from core.jarvis_tts      import _tts_worker as _tw, set_speaking, speak, speak_error
from core.jarvis_prompt   import _load_system_prompt, _build_system_prompt
from core.jarvis_utils    import _is_greeting, calculate
from core.jarvis_script_lang import _auto_switch_language
from core.vad_buffer      import _VADBuffer
from memory.memory_manager import load_memory
from core.llm_client      import ensure_ollama_running, warmup_model, get_llm_provider
from actions.timer_scheduler import set_on_fire as timer_set_callback
from core.scheduler       import get_scheduler


def _load_config() -> dict:
    from memory.config_manager import load_config as _lc
    return _lc()


class JarvisLocal:
    """
    Main assistant class.
    Replaces JarvisLive (Gemini Live API) with:
      STT (Whisper/Vosk) → Ollama LLM (tool calling) → TTS (Edge/Kokoro/ElevenLabs)
    """
    def __init__(self, ui: JarvisUI):
        self.ui               = ui
        self._config          = _load_config()
        self._stt             = None
        self._tts             = None
        self._tts_ready       = threading.Event()   # set when TTS engine is loaded
        self._speaking        = False
        self._speaking_lock   = threading.Lock()
        self._text_queue:     queue.Queue = queue.Queue()
        self._tts_queue:      queue.Queue = queue.Queue()
        self._conversation:   list[dict]  = []
        self._conv_lock = threading.Lock()
        self._generation = 0
        self._processing_lock = threading.Lock()
        self._prefetch_thread = None
        self._prefetched_vec = ""
        self._prefetched_skill = ""
        self._last_intent = None
        self.ui.on_text_command = self._on_text_command
        self._current_language = "en"
        # ── GWS logging ───────────────────────────────────────────────────
        from main import BASE_DIR
        _gws_log_dir = BASE_DIR / "logs"
        _gws_log_dir.mkdir(parents=True, exist_ok=True)
        _gws_handler = logging.FileHandler(str(_gws_log_dir / "gws.log"))
        _gws_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        _gws = logging.getLogger("gws_bridge")
        _gws.addHandler(_gws_handler)
        _gws.setLevel(logging.DEBUG)
        _gws.propagate = False
        # ── Timer / Scheduler callback ──────────────────────────────────────
        logger = logging.getLogger("jarvis")
        def _timer_fired(name_or_msg: str, action: str = "", params: dict = None):
            self.speak(f"{name_or_msg}")
            self.ui.log(f"[Timer] {name_or_msg}")
            p = params or {}
            act = p.get("action", action or "")
            if act in ("shutdown", "restart", "sleep"):
                logger.info("Timer triggered system action: %s", act)
                self.ui.log(f"[Timer] executing: {act}")
                import subprocess, shlex
                cmds = {"shutdown": "shutdown -h now", "restart": "shutdown -r now",
                        "sleep": "systemctl suspend"}
                subprocess.Popen(shlex.split(cmds[act]))
            elif act and act not in ("", "speak"):
                logger.info("Running scheduled action: %s", act)
        timer_set_callback(_timer_fired)

    # ------------------------------------------------------------------
    # Speech helpers (used by every core/jarvis_* module)
    # ------------------------------------------------------------------
    def speak(self, text: str) -> None:
        speak(self, text)

    def set_speaking(self, value: bool) -> None:
        set_speaking(self, value)

    # ------------------------------------------------------------------
    # Auto-detect and switch TTS language
    # ------------------------------------------------------------------
    def _auto_switch_language(self, text: str) -> None:
        self._current_language = _auto_switch_language(self, text)

    # ------------------------------------------------------------------
    # Tool execution — thin wrapper around core/tools/executor.py
    # ------------------------------------------------------------------
    def execute_tool(self, name: str, args: dict) -> str:
        return execute_tool(self.ui, name, args, speak=self.speak,
                            run_async=self._run_async)

    # Aliases expected by extracted core/jarvis_llm.py (kept names)
    def _execute_tool(self, name: str, args: dict) -> str:
        return self.execute_tool(name, args)

    def _run_async(self, coro):
        return _ra(coro)

    def _build_system_prompt(self, user_text: str = "") -> str:
        return _build_system_prompt(self, user_text)

    # ------------------------------------------------------------------
    # Text command entry
    # ------------------------------------------------------------------
    def _on_text_command(self, text: str) -> None:
        self._generation += 1  # invalidates any in-flight _process_message with old gen
        self._text_queue.put(text)

    # ------------------------------------------------------------------
    # Reconfiguration (from UI overlay)
    # ------------------------------------------------------------------
    def reconfigure(self, new_config: dict) -> None:
        do_reconfigure(self, new_config)

    # ------------------------------------------------------------------
    # LLM turn (stream + overlapped TTS)
    # ------------------------------------------------------------------
    def process_message(self, user_text: str) -> None:
        _pm(self, user_text)

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------
    def run(self) -> None:
        """
        Startup strategy — optimised for minimum time-to-interactive:
        1. LLM warmup + STT load  →  parallel, fast (~3s)
        2. TTS load               →  parallel, slow (~20s for Kokoro)
        3. Wait only for (1)      →  go online immediately
        4. TTS finishes in BG     →  queued speech plays automatically
        """
        try:
            self.ui.on_reconfigure = self.reconfigure
            # ── LLM Server ───────────────────────────────────────────────
            provider = get_llm_provider()
            self.ui.write_log(f"SYS: Checking {provider}…")
            if ensure_ollama_running():
                self.ui.write_log(f"SYS: {provider} OK.")
            else:
                self.ui.write_log(f"ERR: {provider} unavailable.")
            # ── Config ────────────────────────────────────────────────────
            stt_engine   = self._config.get("stt_engine",   "whisper").lower()
            stt_language = self._config.get("stt_language", "auto")
            stt_model    = self._config.get("stt_model",    "base")
            tts_engine   = self._config.get("tts_engine",   "edgetts").lower()
            # ── Startup progress panel ────────────────────────────────────
            self.ui.show_startup_panel()
            _warmup_done = threading.Event()
            _stt_done    = threading.Event()
            # ── LLM warmup thread ─────────────────────────────────────────
            def _do_warmup():
                try:
                    warmup_model(system_prompt=_load_system_prompt())
                    self.ui.write_log("SYS: LLM ready.")
                except Exception as e:
                    self.ui.write_log(f"ERR: LLM warmup — {e}")
                finally:
                    _warmup_done.set()
            # ── STT load thread ───────────────────────────────────────────
            def _do_stt():
                try:
                    self.ui.write_log(f"SYS: Loading {stt_engine.upper()} STT…")
                    if stt_engine == "vosk":
                        from core.stt import VoskSTT
                        self._stt = VoskSTT(
                            self._config.get("vosk_model_path"),
                            language=stt_language)
                    else:
                        from core.stt import WhisperSTT
                        self._stt = WhisperSTT(stt_model, language=stt_language)
                    self.ui.write_log("SYS: STT ready.")
                    self.ui.mark_startup_ready("stt")
                except Exception as e:
                    self.ui.write_log(f"ERR: STT — {e}")
                    self.ui.mark_startup_ready("stt", error=True)
                finally:
                    _stt_done.set()
            # ── TTS load thread — does NOT block going online ─────────────
            def _do_tts():
                try:
                    self.ui.write_log(f"SYS: Loading {tts_engine.upper()} TTS…")
                    if tts_engine == "kokoro":
                        self.ui.write_log("SYS: Kokoro — loading model + compiling JIT…")
                    from core.tts import create_tts_player
                    self._tts = create_tts_player(self._config)
                    self._tts_ready.set()          # unblock _tts_worker
                    self.ui.write_log("SYS: TTS ready.")
                    self.ui.mark_startup_ready("tts")
                    self.ui.set_startup_status("● All systems ready.")
                    self.ui.hide_startup_panel()
                    self.speak("Jarvis fully online.")
                except Exception as e:
                    traceback.print_exc()
                    self.ui.write_log(f"ERR: TTS — {e}")
                    self.ui.mark_startup_ready("tts", error=True)
                    self._tts_ready.set()
            # Launch all three simultaneously
            self.ui.write_log("SYS: Loading systems in parallel…")
            threading.Thread(target=_do_warmup, daemon=True).start()
            threading.Thread(target=_do_stt,    daemon=True).start()
            threading.Thread(target=_do_tts,    daemon=True).start()
            # ── Wait ONLY for STT + LLM (fast) ────────────────────────────
            _warmup_done.wait(timeout=15)
            _stt_done.wait(timeout=60)
            # ── Start background services ──────────────────────────────────
            def _scheduler_executor(name: str, command: str, job_type: str):
                if job_type == "shell":
                    from actions.computer_control import computer_control
                    r = computer_control(
                        parameters={"action": "run_command", "command": command},
                        player=self.ui)
                    self.ui.write_log(f"SCHED: {name} → {r[:80]}")
                elif job_type == "agent":
                    from agent.executor import AgentExecutor
                    try:
                        r = AgentExecutor().execute(goal=command, speak=self.speak)
                        self.ui.write_log(f"SCHED-AGENT: {name} → {str(r)[:80]}")
                    except Exception as e:
                        self.ui.write_log(f"SCHED-AGENT: {name} failed: {e}")
                else:
                    self.ui.write_log(f"SCHED: Unknown job type '{job_type}' for '{name}'")
            get_scheduler().set_executor(_scheduler_executor)
            get_scheduler().start()
            self.ui.write_log("SYS: Scheduler started.")
            # ── Go online immediately ──────────────────────────────────────
            self.ui.write_log("SYS: JARVIS online.")
            self.ui.set_state("LISTENING")
            self.ui.set_startup_status("● JARVIS online · Voice loading in background…")
            # ── Fetch location in background (cached for later use) ───────
            _loc_set = False
            def _init_location():
                nonlocal _loc_set
                try:
                    from actions.get_location import get_location
                    r = get_location(player=self.ui, force_refresh=True)
                    import re
                    m = re.search(r"currently in ([^,]+)", r)
                    if m:
                        self.ui.set_location(m.group(1).strip())
                        _loc_set = True
                except Exception:
                    pass
                if not _loc_set:
                    try:
                        from actions.get_location import _ip_location
                        ip_data = _ip_location()
                        if ip_data and ip_data.get("city"):
                            self.ui.set_location(ip_data["city"])
                    except Exception:
                        pass
            threading.Thread(target=_init_location, daemon=True).start()
            threading.Thread(target=self._tts_worker,        daemon=True).start()
            threading.Thread(target=self._text_command_loop,  daemon=True).start()
            # STT loop — blocks this thread forever
            if stt_engine == "vosk":
                _lv(self)
            else:
                _lw(self)
        except Exception as e:
            self.ui.write_log(f"ERR: Init failed — {e}")
            traceback.print_exc()

    # ------------------------------------------------------------------
    # Thread entry points (delegated from core.jarvis_*)
    # ------------------------------------------------------------------
    def _tts_worker(self) -> None:
        _tw(self)

    def _text_command_loop(self) -> None:
        _tcl(self)
