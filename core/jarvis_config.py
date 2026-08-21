"""Runtime reconfiguration."""
from __future__ import annotations
import sys
import subprocess
import shutil
import logging
import traceback
import threading

from core.llm_client import invalidate_config_cache

def reconfigure(self, new_config: dict) -> None:
    """Non-blocking: spawns a background thread to install + reload."""
    threading.Thread(
        target=_do_reconfigure, args=(self, new_config), daemon=True
    ).start()

def _do_reconfigure(self, new_config: dict) -> None:
    old_stt_engine = self._config.get("stt_engine", "whisper").lower()
    old_stt_model  = self._config.get("stt_model", "tiny").lower()
    old_tts_engine = self._config.get("tts_engine", "edgetts").lower()
    old_tts_voice  = self._config.get("tts_voice", "")
    old_llm_model  = self._config.get("llm_model", "")
    new_stt_engine = new_config.get("stt_engine", "whisper").lower()
    new_stt_model  = new_config.get("stt_model", "tiny").lower()
    new_tts_engine = new_config.get("tts_engine", "edgetts").lower()
    new_tts_voice  = new_config.get("tts_voice", "")
    self._config = new_config
    invalidate_config_cache()

    # Install any packages required by the new config (fast if already installed)
    try:
        from core.installer import install_for_config
        install_for_config(new_config, log=self.ui.write_log)
    except Exception as e:
        self.ui.write_log(f"ERR: Dependency install — {e}")

    # TTS: only reload if engine or voice changed
    tts_changed = (
        new_tts_engine != old_tts_engine
        or new_tts_voice != old_tts_voice
    )
    if tts_changed:
        try:
            from core.tts import create_tts_player
            self._tts = create_tts_player(new_config)
            self._tts_ready.set()
            self.ui.write_log("SYS: TTS reconfigured.")
        except Exception as e:
            self.ui.write_log(f"ERR: TTS reconfigure — {e}")

    # STT: only reload if engine type or model changed
    stt_changed = (
        old_stt_engine != new_stt_engine
        or old_stt_model != new_stt_model
    )
    if stt_changed and old_stt_engine == new_stt_engine:
        try:
            stt_language = new_config.get("stt_language", "auto")
            if new_stt_engine == "vosk":
                from core.stt import VoskSTT
                self._stt = VoskSTT(new_config.get("vosk_model_path"), language=stt_language)
            else:
                from core.stt import WhisperSTT
                self._stt = WhisperSTT(new_stt_model, language=stt_language)
            self.ui.write_log("SYS: STT reconfigured.")
        except Exception as e:
            self.ui.write_log(f"ERR: STT reconfigure — {e}")
    elif stt_changed:
        self.ui.write_log("SYS: STT engine changed — restart required.")

    # LLM warmup if model changed
    if new_config.get("llm_model", "") != old_llm_model:
        self.ui.write_log("SYS: Warming up new LLM model…")
        from core.llm_client import warmup_model
        warmup_model()
        self.ui.write_log("SYS: New LLM model ready.")

    if stt_changed and old_stt_engine != new_stt_engine:
        self.speak("LLM and TTS updated. Restart for speech engine change.")
    elif tts_changed or stt_changed:
        self.speak("Configuration applied.")

# ------------------------------------------------------------------
# Text command (from UI input box)
# ------------------------------------------------------------------

