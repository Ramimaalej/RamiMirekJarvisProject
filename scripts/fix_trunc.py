"""Fix truncated tails of the extracted modules."""
import re
from pathlib import Path

BASE = Path("core")

# 1. jarvis_script_lang.py — restore body of _detect_script_language from main.py
main = Path("main.py").read_text()
ml = main.split("\n")
body = "\n".join(ml[201:212])  # lines 202-212 (def at 202, body until "return None")
p = BASE / "jarvis_script_lang.py"
t = p.read_text()
# replace the empty def line with def + body
t = t.replace("def _detect_script_language(text: str) -> str | None:\ndef _auto_switch_language",
              body.rstrip() + "\n\ndef _auto_switch_language")
p.write_text(t)
print("script_lang fixed, len:", len(t.splitlines()))

# 2. jarvis_utils.py — cut at _load_system_prompt header and check end
p = BASE / "jarvis_utils.py"
t = p.read_text()
# keep everything up to the _load_system_prompt marker (line starting with "def _load_system_prompt")
t = t.split("def _load_system_prompt")[0]
t = t.rstrip() + "\n"
p.write_text(t)
print("utils fixed, len:", len(t.splitlines()))
print("utils tail:", t[-150:])

# 3. tools/executor.py — remove trailing @staticmethod/_run_async stub
p = BASE / "tools" / "executor.py"
t = p.read_text()
idx = t.find("# Async helper for Google Workspace tools")
t = t[:idx].rstrip() + "\n"
p.write_text(t)
print("executor fixed, len:", len(t.splitlines()))
print("executor tail:", t[-120:])
