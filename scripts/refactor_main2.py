"""Refactor main.py — full extraction, corrected boundaries.

Extracted modules (all in core/):
  jarvis_script_lang.py   — _SCRIPT_RANGES + _detect_script_language
  tools/declarations.py   — TOOL_DECLARATIONS + _convert_* + _to_ollama_tools
  tools/executor.py       — _execute_tool -> execute_tool(ui, name, args)
  jarvis_utils.py         — _is_greeting + calculate
  jarvis_prompt.py        — _load_system_prompt + _build_system_prompt
  jarvis_stt.py           — _VADBuffer + _listen_whisper + _listen_vosk
  jarvis_tts.py           — _tts_worker + speak* + set_speaking
  jarvis_llm.py           — _process_message + _prefetch_context + _run_async
  jarvis_config.py        — _do_reconfigure + reconfigure
  jarvis_scheduler.py     — _scheduler_executor (built inside run())
  jarvis_location.py      — _init_location (built inside run())
  jarvis_warmup.py        — _do_warmup / _do_stt / _do_tts (built inside run())
  jarvis_core.py          — JarvisLocal skeleton + main() + bootstrap
"""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MAIN = BASE / "main.py"
lines = MAIN.read_text(encoding="utf-8").split("\n")

os.makedirs(BASE / "core" / "tools", exist_ok=True)
if not (BASE / "core" / "tools" / "__init__.py").exists():
    (BASE / "core" / "tools" / "__init__.py").write_text(
        '"""Tool execution & declarations."""\n', encoding="utf-8")


def grab(start, end):
    return lines[start - 1:end]


def write(name, header, chunk, deindent=0):
    out = chunk
    if deindent:
        out = [ln[deindent:] if ln.startswith(" " * deindent) else ln for ln in out]
    txt = header + "\n".join(out) + "\n"
    (BASE / "core" / name).write_text(txt, encoding="utf-8")
    return len(out)


# ---------------------------------------------------------------------------
# 1. Script language  (191 -> 202.. actually 191 -> end of func = 201)
# ---------------------------------------------------------------------------
n = write("jarvis_script_lang.py",
          '"""Unicode script-based language detection."""\n'
          "from __future__ import annotations\n\n",
          grab(191, 202))
print("jarvis_script_lang.py:", n)

# ---------------------------------------------------------------------------
# 2. Tool declarations + conversions (202..1684 incl. TOOL_DECLARATIONS start)
#    TOOL_DECLARATIONS begins at line 207-ish (after xhost guard); we take
#    from the xhost guard to just before _load_config (1683).
# ---------------------------------------------------------------------------
n = write("tools/declarations.py",
          '"""Tool declarations (Gemini format) + Ollama conversion utilities."""\n'
          "from __future__ import annotations\n\n",
          grab(213, 1683))
print("tools/declarations.py:", n)

# ---------------------------------------------------------------------------
# 3. Utils (_is_greeting + calculate)
# ---------------------------------------------------------------------------
n = write("jarvis_utils.py",
          '"""Small utilities."""\n'
          "from __future__ import annotations\n\n",
          grab(1707, 1871))
print("jarvis_utils.py:", n)

# ---------------------------------------------------------------------------
# 4. Prompt (_load_system_prompt + _build_system_prompt 1871 -> 2103)
# ---------------------------------------------------------------------------
n = write("jarvis_prompt.py",
          '"""System-prompt loading & building."""\n'
          "from __future__ import annotations\n\n",
          grab(1871, 1887))
print("jarvis_prompt.py:", n)

# ---------------------------------------------------------------------------
# 5. VAD buffer (1890 -> 1948)
# ---------------------------------------------------------------------------
n = write("vad_buffer.py",
          '"""Voice Activity Detection buffer."""\n'
          "from __future__ import annotations\n\n",
          grab(1890, 1948))
print("vad_buffer.py:", n)

# ---------------------------------------------------------------------------
# 6. STT: _listen_whisper (3670 -> 3733), _listen_vosk (3733 -> 3771),
#    _text_command_loop (3771 -> 3789)
# ---------------------------------------------------------------------------
stt_chunk = grab(3670, 3788)
stt_chunk = [ln[4:] if ln.startswith("    ") else ln for ln in stt_chunk]
n = write("jarvis_stt.py",
          '"""Speech-to-text listeners (Whisper / Vosk)."""\n'
          "from __future__ import annotations\n\n",
          stt_chunk)
print("jarvis_stt.py:", n)

# ---------------------------------------------------------------------------
# 7. TTS: _tts_worker (2103 -> 2150)  (incl. set_speaking, speak, speak_error)
# ---------------------------------------------------------------------------
tts_chunk = grab(2103, 2145)
tts_chunk = [ln[4:] if ln.startswith("    ") else ln for ln in tts_chunk]
n = write("jarvis_tts.py",
          '"""Text-to-speech worker + speak helpers."""\n'
          "from __future__ import annotations\n\n",
          tts_chunk)
print("jarvis_tts.py:", n)

# ---------------------------------------------------------------------------
# 8. LLM turn: _process_message (3411 -> 3670) + _prefetch_context (3403->3411)
#    + _run_async (3390 -> 3403)
# ---------------------------------------------------------------------------
llm_chunk = grab(3390, 3669)
llm_chunk = [ln[4:] if ln.startswith("    ") else ln for ln in llm_chunk]
n = write("jarvis_llm.py",
          '"""LLM turn processing (stream + overlapped TTS)."""\n'
          "from __future__ import annotations\n\n",
          llm_chunk)
print("jarvis_llm.py:", n)

# ---------------------------------------------------------------------------
# 9. Config: reconfigure + _do_reconfigure (2150 -> 2226)
# ---------------------------------------------------------------------------
cfg_chunk = grab(2150, 2225)
cfg_chunk = [ln[4:] if ln.startswith("    ") else ln for ln in cfg_chunk]
n = write("jarvis_config.py",
          '"""Runtime reconfiguration."""\n'
          "from __future__ import annotations\n\n",
          cfg_chunk)
print("jarvis_config.py:", n)

# ---------------------------------------------------------------------------
# 10. Auto-switch language (2008 -> 2034) — pure function
# ---------------------------------------------------------------------------
asl_chunk = grab(2008, 2031)
asl_chunk = [ln[4:] if ln.startswith("    ") else ln for ln in asl_chunk]
_sl_existing = (BASE / "core" / "jarvis_script_lang.py").read_text(encoding="utf-8")
(BASE / "core" / "jarvis_script_lang.py").write_text(
    _sl_existing.rstrip() + "\n\n" + "\n".join(asl_chunk) + "\n",
    encoding="utf-8")
print("jarvis_script_lang.py (with auto_switch)")

# ---------------------------------------------------------------------------
# 11. build_system_prompt (2034 -> 2103) — already inside jarvis_prompt.py
#     (grab 1871-1890 only had _load_system_prompt; add 2034-2103)
# ---------------------------------------------------------------------------
build_chunk = grab(2033, 2095)
build_chunk = [ln[4:] if ln.startswith("    ") else ln for ln in build_chunk]
prompt_text = (BASE / "core" / "jarvis_prompt.py").read_text(encoding="utf-8")
assert "_tts_worker" not in prompt_text, "jarvis_prompt.py boundary still wrong"
(BASE / "core" / "jarvis_prompt.py").write_text(
    prompt_text.rstrip() + "\n\n" + "\n".join(build_chunk) + "\n", encoding="utf-8")
print("jarvis_prompt.py: updated (load + build)")

print("DONE - phase A")
