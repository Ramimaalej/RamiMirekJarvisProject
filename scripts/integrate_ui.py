"""Integrate the new screens and features into ui.py and actions/intent_router.py."""
import sys

sys.path.insert(0, ".")

# --------------------------------------------------------------- #
# 1. ui.py — add "Ollama" & "Browser" buttons, wire overlays
# --------------------------------------------------------------- #
with open("ui.py", encoding="utf-8") as f:
    src = f.read()

# --- 1a. Menu buttons ------------------------------------------------
old = '''        for label, cb in [
            ("Fullscreen", self._toggle_fullscreen),
            ("Providers", self._show_providers),
            ("Settings", self._show_config),
            ("Connections", self._show_connections),
            ("Island", self._toggle_island),
        ]:'''
new = '''        for label, cb in [
            ("Fullscreen", self._toggle_fullscreen),
            ("Providers", self._show_providers),
            ("Ollama", self._show_ollama_models),
            ("Settings", self._show_config),
            ("Connections", self._show_connections),
            ("Island", self._toggle_island),
        ]:'''
assert old in src, "menu row with Providers not found"
src = src.replace(old, new, 1)

# --- 1b. Ollama models page method -----------------------------------
insert_after = '''        ov.show()
        self._overlay_prov = ov
'''
ollama_block = '''
    def _show_ollama_models(self):
        """Open the Ollama Models manager (install/delete models in one click)."""
        if getattr(self, "_overlay_ollama", None) and self._overlay_ollama.isVisible():
            return
        from core.ollama_models_overlay import OllamaModelsOverlay
        ov = OllamaModelsOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = min(cw.width() - 20, 880), min(cw.height() - 20, 560)
        ov.setGeometry((cw.width() - ow) // 2, (cw.height() - oh) // 2, ow, oh)
        ov.show()
        self._overlay_ollama = ov
'''
assert insert_after in src, "insert anchor not found"
src = src.replace(insert_after, insert_after + ollama_block, 1)

with open("ui.py", "w", encoding="utf-8") as f:
    f.write(src)
print("ui.py updated OK")

# --------------------------------------------------------------- #
# 2. actions/intent_router.py — register fast_browser routes
# --------------------------------------------------------------- #
with open("actions/intent_router.py", encoding="utf-8") as f:
    rtr = f.read()

old = '''    # ── Browser / Web ────────────────────────────────────────────────
    {
        "name": "open_app",
        "subsystem": "browser",
        "patterns": [
            r"^(open|launch|start|run|go\\s+to)\\s+",
        ],
        "handler": "open_app",
        "params": {},
        "requires_ai": False,
    },'''
new = '''    # ── Browser / Web ────────────────────────────────────────────────
    {
        "name": "fast_browser",
        "subsystem": "browser",
        "patterns": [
            r"^(open|go\\s+to|visit|navigate\\s+to)\\s+(https?://|www\\.|[a-z0-9\\-]+\\.[a-z])",
            r"^click\\s+.+",
            r"^scroll\\s+(up|down)",
            r"^(refresh|reload|back|new\\s+tab|close\\s+tab)",
            r"^grab\\s+(the\\s+)?page",
            r"^screenshot",
        ],
        "handler": "fast_browser",
        "params": {},
        "requires_ai": False,
        "priority": "high",
    },
    {
        "name": "open_app",
        "subsystem": "browser",
        "patterns": [
            r"^(open|launch|start|run|go\\s+to)\\s+",
        ],
        "handler": "open_app",
        "params": {},
        "requires_ai": False,
    },'''
assert old in rtr, "intent router browser block not found"
rtr = rtr.replace(old, new, 1)

with open("actions/intent_router.py", "w", encoding="utf-8") as f:
    f.write(rtr)
print("intent_router.py updated OK")
