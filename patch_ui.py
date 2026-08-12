import sys

with open("ui.py", "r") as f:
    content = f.read()

# Add Providers button
old_btns = """        for label, cb in [
            ("Fullscreen", self._toggle_fullscreen),
            ("Settings", self._show_config),
            ("Island", self._toggle_island),
        ]:"""
new_btns = """        for label, cb in [
            ("Fullscreen", self._toggle_fullscreen),
            ("Settings", self._show_config),
            ("Providers", self._show_providers),
            ("Island", self._toggle_island),
        ]:"""
content = content.replace(old_btns, new_btns)

# Add methods
old_methods = """        if self._on_reconfigure_cb:
            self._on_reconfigure_cb(cfg)"""
            
new_methods = """        if self._on_reconfigure_cb:
            self._on_reconfigure_cb(cfg)

    def _show_providers(self):
        if getattr(self, "_overlay_prov", None) and self._overlay_prov.isVisible():
            return
        import json
        from pathlib import Path
        current = {}
        try:
            current = json.loads(Path("config/api_keys.json").read_text(encoding="utf-8"))
        except Exception:
            pass
        ov = ProvidersOverlay(self.centralWidget(), initial=current)
        cw = self.centralWidget()
        ow, oh = 800, 500
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_providers_done)
        ov.show()
        self._overlay_prov = ov

    def _on_providers_done(self, diff_json: str):
        import json
        import os
        from pathlib import Path
        try:
            diff = json.loads(diff_json)
        except Exception:
            diff = {}
        
        current = {}
        API_FILE = Path("config/api_keys.json")
        try:
            current = json.loads(API_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        
        current.update(diff)
        
        os.makedirs("config", exist_ok=True)
        API_FILE.write_text(json.dumps(current, indent=4), encoding="utf-8")
        if getattr(self, "_overlay_prov", None):
            self._overlay_prov.hide()
            self._overlay_prov = None
            
        self._log.append_log("SYS: Providers updated.")
        if self._on_reconfigure_cb:
            self._on_reconfigure_cb(current)"""

content = content.replace(old_methods, new_methods)

with open("ui.py", "w") as f:
    f.write(content)
