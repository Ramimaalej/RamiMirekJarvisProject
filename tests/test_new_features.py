"""Headless smoke tests for the new features:
  * Provider Overlay (selection + auto model discovery)
  * Ollama Models manager (logic, without a real Ollama server)
  * Fast Browser dispatcher (parsing, no real browser)

Run:  QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_new_features.py -v
"""
import json
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))


# --------------------------------------------------------------- #
# 1. Provider Overlay
# --------------------------------------------------------------- #
def test_provider_overlay_creates(qapp):
    from core.provider_overlay import ProviderOverlay
    ov = ProviderOverlay(initial={"llm_provider": "ollama", "llm_model": "qwen3:8b"})
    assert len(ov._cards) == 6
    assert ov._cards["ollama"]._model_combo.count() >= 5
    ov._submit()
    ov.deleteLater()


def test_provider_overlay_discovery(qapp):
    from core.provider_overlay import ProviderOverlay
    ov = ProviderOverlay(initial={"llm_provider": "groq"})
    emitted = []
    ov.done.connect(lambda j: emitted.append(json.loads(j)))
    ov._discover_worker()
    time.sleep(1)
    assert ov._discovery
    ov._select_provider("groq")
    ov._submit()
    cfg = emitted[0]
    assert cfg["llm_provider"] == "groq"
    assert cfg["llm_model"]
    ov.deleteLater()


# --------------------------------------------------------------- #
# 2. Ollama Models (logic) — mocked requests
# --------------------------------------------------------------- #
def test_ollama_list_with_server():
    from core import ollama_models as om
    fake = {"models": [{
        "name": "qwen3:8b", "size": 5 * 1024 ** 3, "modified_at": "2026-01-01T00:00:00Z",
        "details": {"family": "qwen3"},
    }]}
    with mock.patch("core.ollama_models.requests.get") as g:
        g.return_value.json.return_value = fake
        g.return_value.status_code = 200
        models = om.list_local_models({})
    assert len(models) == 1
    assert models[0]["id"] == "qwen3:8b"
    assert models[0]["size_gb"] == 5.0


def test_ollama_offline():
    from core import ollama_models as om
    with mock.patch("core.ollama_models.requests.get", side_effect=RuntimeError):
        assert om.list_local_models({}) == []
        assert not om.is_running("http://localhost:11434")


# --------------------------------------------------------------- #
# 3. Fast Browser dispatcher (no real browser)
# --------------------------------------------------------------- #
def test_fast_browser_no_module_load():
    """fast_browser action imports core.fast_browser without crashing."""
    import actions.fast_browser as fb
    assert fb.CAPABILITY["handler"] == "fast_browser"


def test_fast_browser_dispatch_no_server():
    """Without a running browser or playwright installed, commands return an error string (never crash)."""
    from core.fast_browser import get_fast_browser
    fb = get_fast_browser()
    res = fb.run("open https://example.com", timeout=5)
    assert isinstance(res, str)
    print("fast_browser result (no browser):", res)


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
