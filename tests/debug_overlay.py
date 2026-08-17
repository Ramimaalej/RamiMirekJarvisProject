import sys
sys.path.insert(0, ".")
from PyQt6.QtWidgets import QApplication
app = QApplication([])
from ui import C
C.apply_theme(False)
from core.provider_overlay import ProviderOverlay

ov = ProviderOverlay(initial={"llm_provider": "ollama", "llm_model": "qwen2.5:7b"})
for pid, card in ov._card_widgets.items():
    print(pid, "count=", card._model_combo.count(), "text=", card._model_combo.currentText())
