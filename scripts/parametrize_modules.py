"""Post-process extracted modules:
- convert `def _fn(self, ...)` -> `def _fn(self, ...)` kept as-is (self = JarvisLocal instance passed by caller)
  Actually the modules call them as free functions: process_message(self, text), etc.
- add missing imports so each module compiles standalone
- tools/executor: replace self.ui / self.speak / self._run_async with params
"""
import re
from pathlib import Path

BASE = Path("core")


def add_imports(text: str, imports: list[str]) -> str:
    header_end = text.find("\n") + 1
    head = text[:header_end]
    body = text[header_end:]
    imp = "\n".join(imports) + "\n\n"
    return head + imp + body


def ensure_import(text: str, imp: str) -> str:
    if imp in text:
        return text
    return text.replace("from __future__ import annotations\n",
                        f"from __future__ import annotations\n{imp}\n", 1)


files = {
    "jarvis_llm.py": ["import asyncio", "import json", "import logging",
                      "import queue", "import re", "import time", "import traceback"],
    "jarvis_stt.py": ["import queue", "import re", "import time", "import traceback"],
    "jarvis_tts.py": ["import queue", "import logging", "import traceback"],
    "jarvis_config.py": ["import threading", "import traceback", "import logging",
                         "import shutil", "import subprocess", "import sys"],
    "jarvis_prompt.py": ["import logging", "import re", "from datetime import datetime",
                         "from pathlib import Path", "import json", "import os"],
    "jarvis_utils.py": ["import re", "import logging", "from typing import Any"],
}
for name, imps in files.items():
    p = BASE / name
    t = p.read_text()
    for imp in imps:
        t = ensure_import(t, imp)
    p.write_text(t)
    print(name, "imports ok")

# ---- jarvis_script_lang.py ----
p = BASE / "jarvis_script_lang.py"
t = p.read_text()
t = ensure_import(t, "import logging\nimport re\nfrom typing import Any")
p.write_text(t)

# ---- tools/executor.py : self.ui -> ui param, self.speak -> speak param,
# self._run_async -> run_async param ----
p = BASE / "tools" / "executor.py"
t = p.read_text()
t = t.replace(
    "def execute_tool(ui, name: str, args: dict) -> str:",
    "def execute_tool(ui, name: str, args: dict,\n"
    "                 speak=lambda x: None,\n"
    "                 run_async=lambda c: None,\n"
    "                 shutdown=lambda: None,\n"
    "                 ) -> str:")
# self.ui -> ui everywhere
t = t.replace("self.ui", "ui")
# self.speak -> speak
t = re.sub(r"\bself\.speak\b", "speak", t)
# self._run_async -> run_async
t = re.sub(r"\bself\._run_async\b", "run_async", t)
# self._shutdown -> shutdown (check occurrence)
t = re.sub(r"\bself\._shutdown\b", "shutdown", t)
p.write_text(t)
print("executor parametrized")

# ---- verify no stray `self.` remain in executor except inside strings ----
remaining = [ln for ln in t.split("\n") if re.search(r"\bself\.", ln)
             and not ln.strip().startswith("#")]
print("executor remaining self refs:", len(remaining))
for ln in remaining[:10]:
    print("   :", ln.strip()[:100])
