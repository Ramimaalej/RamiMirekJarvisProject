import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
sys.path.insert(0, ".")
from PyQt6.QtWidgets import QApplication
app = QApplication([])
from ui import C
C.apply_theme(False)
from core import provider_overlay as po
orig = po.ProviderOverlay._fill_models
def dbg(self, pid, models):
    card = self._card_widgets.get(pid)
    print(pid, "has_combo:", hasattr(card, "_model_combo"), "models:", models[:3])
    orig(self, pid, models)
    print("  -> count:", card._model_combo.count())
po.ProviderOverlay._fill_models = dbg
from core.provider_overlay import ProviderOverlay
ov = ProviderOverlay(initial={"llm_provider": "ollama"})
