"""Refactor main.py (4000 lines) into per-feature modules.

Strategy — extract by line-ranges (fidèle au code original, zéro sémantique
modifiée), puis :
  1. core/tools/*          : _execute_tool + TOOL_DECLARATIONS + conversions
  2. core/jarvis_*.py      : STT / TTS / LLM / orchestrateur / prompt / ...
  3. main.py               : relancé au strict minimum (bootstrap + launcher)
"""
import os
import re
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MAIN = BASE / "main.py"

main_text = MAIN.read_text(encoding="utf-8")
lines = main_text.split("\n")
LINE = {i + 1: ln for i, ln in enumerate(lines)}


def grab(start, end):
    return "\n".join(lines[start - 1:end])


os.makedirs(BASE / "core" / "tools", exist_ok=True)
# keep __init__ importable
(BASE / "core" / "tools" / "__init__.py").write_text(
    '"""Tool execution & declarations — extracted from main.py."""\n', encoding="utf-8")

# ---------------------------------------------------------------------------
# 1. Script language + TOOLS (202 -> 1684)  [detect + declare + convert]
# ---------------------------------------------------------------------------
chunk_tools_full = grab(202, 1684)

# Split around TOOL_DECLARATIONS marker
m_decl = chunk_tools_full.find("TOOL_DECLARATIONS = [")
m_convert = chunk_tools_full.find("def _convert_type(")

detect_block = chunk_tools_full[:m_decl].split("\n", 1)[1]  # drop first-def def line? keep all
tools_decl   = chunk_tools_full[m_decl:m_convert]
convert_block = chunk_tools_full[m_convert:]

# --- detect script language ---
# find _SCRIPT_RANGES start (before the def)
m_ranges = chunk_tools_full.find("_SCRIPT_RANGES")
detect_text = chunk_tools_full[m_ranges:m_decl].strip() + "\n"
(BASE / "core" / "jarvis_script_lang.py").write_text(
    '"""Unicode script-based language detection (extracted from main.py)."""\n'
    "from __future__ import annotations\n\n" + detect_text + "\n",
    encoding="utf-8")

# --- tool declarations + conversions ---
(BASE / "core" / "tools" / "declarations.py").write_text(
    '"""Tool declarations (Gemini format) + Ollama conversion utilities."""\n'
    "from __future__ import annotations\n\n" + tools_decl + "\n" + convert_block + "\n",
    encoding="utf-8")

# ---------------------------------------------------------------------------
# 2. _execute_tool  (2234 -> 3390)  — biggest block: per-tool handler code
# ---------------------------------------------------------------------------
exec_tool = grab(2234, 3390)
# Replace "self.ui" references with a passed-in "ui" (method signature change)
exec_tool = exec_tool.replace("def _execute_tool(self, name: str, args: dict) -> str:",
                              "def execute_tool(ui, name: str, args: dict) -> str:")
# Indent stays as-is (was inside class); remove first level of indentation (4 spaces)
exec_tool_lines = []
for ln in exec_tool.split("\n"):
    if ln.startswith("    "):
        exec_tool_lines.append(ln[4:])
    else:
        exec_tool_lines.append(ln)
exec_tool_out = "\n".join(exec_tool_lines)
(BASE / "core" / "tools" / "executor.py").write_text(
    '"""Per-tool execution logic (extracted from main.py _execute_tool)."""\n'
    "from __future__ import annotations\n\n" + exec_tool_out + "\n",
    encoding="utf-8")

# ---------------------------------------------------------------------------
# 3. Small utility blocks
# ---------------------------------------------------------------------------
is_greeting = grab(1707, 1720)
calculate   = grab(1720, 1871)
load_prompt = grab(1871, 1890)
vad_buffer  = grab(1890, 1948)

(BASE / "core" / "jarvis_utils.py").write_text(
    '"""Small utilities extracted from main.py."""\n'
    "from __future__ import annotations\n\n" + is_greeting + "\n\n" + calculate + "\n",
    encoding="utf-8")

(BASE / "core" / "jarvis_prompt.py").write_text(
    '"""System-prompt loading & building (extracted from main.py)."""\n'
    "from __future__ import annotations\n\n" + load_prompt + "\n",
    encoding="utf-8")

(BASE / "core" / "vad_buffer.py").write_text(
    '"""Voice Activity Detection buffer (extracted from main.py)."""\n'
    "from __future__ import annotations\n\n" + vad_buffer + "\n",
    encoding="utf-8")

print("Chunks written.")
print("  tools/declarations.py :", len(tools_decl.splitlines()), "lines")
print("  tools/executor.py     :", len(exec_tool_out.splitlines()), "lines")
print("  jarvis_script_lang.py :", len(detect_text.splitlines()), "lines")
