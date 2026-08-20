"""Headless smoke test for the Provider Overlay (grid-of-cards design) — run with:
QT_QPA_PLATFORM=offscreen pytest tests/test_provider_overlay.py -v
"""
import json
import sys
import time
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


def test_overlay_creation(qapp):
    from core.provider_overlay import ProviderOverlay
    from ui import C as UIC
    UIC.apply_theme(False)
    ov = ProviderOverlay(initial={
        "llm_provider": "ollama",
        "llm_model": "qwen2.5:7b",
    })
    assert ov._selected_pid in ("ollama", "")
    # grid-of-cards design: one card per provider
    assert len(ov._cards) == 6
    # models should be pre-filled from defaults at minimum
    combo = ov._cards["ollama"]._model_combo
    assert combo.count() >= 5
    ov.deleteLater()


def test_discovery_and_submit(qapp):
    from core.provider_overlay import ProviderOverlay
    from ui import C as UIC
    UIC.apply_theme(False)
    ov = ProviderOverlay(initial={"llm_provider": "groq"})
    emitted = []
    ov.done.connect(lambda j: emitted.append(json.loads(j)))
    # run discovery synchronously (it spawns its own thread, give it time)
    ov._discover_worker()
    time.sleep(1)
    assert ov._discovery, "discovery should return statuses for all providers"
    assert all(pid in ov._discovery for pid in
               ["ollama", "groq", "gemini", "nvidia_nim", "openrouter", "openai"])
    ov._select_provider("groq")
    assert ov._selected_pid == "groq"
    ov._submit()
    assert emitted, "done signal should have fired"
    cfg = emitted[0]
    assert cfg["llm_provider"] == "groq"
    assert cfg["llm_model"], "a model must be selected"
    print("submitted:", json.dumps(cfg, indent=2))
    ov.deleteLater()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
