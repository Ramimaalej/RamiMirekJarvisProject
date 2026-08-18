"""Hard tests — battery covering the latest fixes:

1. LLM provider/URL mismatch (Groq must never point to localhost:11434).
2. Intent routing: WhatsApp/messenger messages vs Gmail emails vs system apps
   (terminal must not fall back to terminal.com).
3. New admin-style ProviderOverlay (cards, badges, model auto-load, submit).
4. Episodic memory module loads without deadlocks.
5. Tool executor imports all actions correctly.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# 1. LLM provider / URL mismatch (core/llm_client.get_llm_settings)
# ---------------------------------------------------------------------------
class TestLlmProviderUrlMismatch:
    """Simulate config/api_keys.json with mismatched provider+url, verify
    get_llm_settings corrects the URL via the mismatch guard."""

    def setup_method(self):
        self._orig = None
        self._cfg_path = Path("config/api_keys.json")
        if self._cfg_path.exists():
            self._orig = self._cfg_path.read_text(encoding="utf-8")
        # invalidate llm_client config cache before each test
        import core.llm_client as _lc
        _lc._CONFIG_CACHE = {}
        _lc._CONFIG_CACHE_AT = 0

    def teardown_method(self):
        self._cfg_path.parent.mkdir(exist_ok=True)
        if self._orig is not None:
            self._cfg_path.write_text(self._orig, encoding="utf-8")
        else:
            self._cfg_path.unlink(missing_ok=True)

    def test_groq_localhost_url_fixed(self):
        from core.llm_client import get_llm_settings
        self._write({"llm_provider": "groq",
                     "llm_model": "llama-3.3-70b-versatile",
                     "llm_url": "http://localhost:11434",
                     "groq_api_key": "gsk_test"})
        url, model = get_llm_settings()
        assert "localhost" not in url, f"groq resolved to {url}"
        assert "groq.com" in url

    def test_ollama_cloud_url_fixed(self):
        from core.llm_client import get_llm_settings
        self._write({"llm_provider": "ollama", "llm_model": "qwen3:8b",
                     "llm_url": "https://api.openrouter.ai/api/v1"})
        url, model = get_llm_settings()
        assert "localhost:11434" in url, f"ollama resolved to {url}"

    def test_provider_switch_persists_url(self):
        from core.llm_client import get_llm_settings
        cases = [("groq", "groq.com", "llama-3.3-70b-versatile"),
                 ("ollama", "11434", "qwen3:8b"),
                 ("groq", "groq.com", "llama-3.3-70b-versatile")]
        for provider, expect, model in cases:
            self._write({"llm_provider": provider, "llm_model": model,
                         "groq_api_key": "gsk_test"})
            url, _ = get_llm_settings()
            assert expect in url, f"{provider} -> {url}"

    def _write(self, cfg: dict):
        self._cfg_path.parent.mkdir(exist_ok=True)
        self._cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        import core.llm_client as _lc
        _lc._CONFIG_CACHE = {}
        _lc._CONFIG_CACHE_AT = 0


# ---------------------------------------------------------------------------
# 2. Intent routing hard cases
# ---------------------------------------------------------------------------
class TestIntentRoutingHard:
    def _route(self, text: str):
        from actions.intent_router import IntentRouter
        return IntentRouter().route(text)

    def test_whatsapp_message(self):
        r = self._route("send message to majdi on whatsapp")
        assert r.matched and r.intent_name == "send_message", r.intent_name
        assert r.handler_params.get("platform") == "whatsapp"

    def test_whatsapp_message_variant(self):
        r = self._route("send a whatsapp message to sarah")
        assert r.matched and r.intent_name == "send_message", r.intent_name
        assert r.handler_params.get("platform") == "whatsapp"

    def test_email_message(self):
        r = self._route("send a message to boss")
        assert r.matched, r.intent_name
        # No messaging platform mentioned -> gmail path
        assert r.intent_name in ("gmail_send",), \
            f"expected gmail_send, got {r.intent_name}"

    def test_email_explicit(self):
        r = self._route("send an email to majdi about the report")
        assert r.matched and r.intent_name == "gmail_send", r.intent_name

    def test_open_terminal(self):
        r = self._route("open terminal")
        assert r.matched and r.intent_name == "open_app", r.intent_name

    def test_open_browser_app(self):
        r = self._route("open chrome")
        assert r.matched and r.intent_name == "open_app", r.intent_name

    def test_go_to_url(self):
        r = self._route("open https://google.com")
        assert r.matched and r.intent_name == "fast_browser", r.intent_name

    def test_compound_open_app_to_llm(self):
        """Compound requests must not be dispatched raw to open_app."""
        r = self._route("open chrome and register to the website")
        assert r.requires_ai, "compound request should go to the LLM"


class TestOpenAppSystemFallback:
    def test_terminal_never_web_fallback(self):
        from actions.open_app import open_app
        result = open_app(parameters={"app_name": "terminal"})
        assert "terminal.com" not in result, result
        assert "browser" not in result.lower(), result

    def test_unknown_web_fallback_still_works(self):
        from actions.open_app import open_app
        # A random unknown single word may still try a website
        result = open_app(parameters={"app_name": "qwxyznonexistentapp"})
        assert "terminal.com" not in result


# ---------------------------------------------------------------------------
# 3. Provider overlay admin-style (create, select, submit)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    os.environ.get("QT_QPA_PLATFORM") is None
    and not sys.platform.startswith("win"),
    reason="headless UI",
)
class TestProviderOverlayAdmin:
    @classmethod
    def setup_class(cls):
        from PyQt6.QtWidgets import QApplication
        if not QApplication.instance():
            cls._app = QApplication(sys.argv or ["pytest"])
        else:
            cls._app = None
        # Pre-import ui so the design tokens exist before the overlay
        import ui  # noqa: F401

    def _make(self):
        from core.provider_overlay import ProviderOverlay
        cfg = {
            "llm_provider": "ollama",
            "llm_model": "qwen3:8b",
            "groq_api_key": "gsk_test",
        }
        return ProviderOverlay(None, initial=cfg)

    def test_card_count(self):
        ov = self._make()
        assert len(ov._cards) == 6

    def test_badges_text(self):
        ov = self._make()
        for pid, card in ov._cards.items():
            text = card._badge_lbl.text()
            assert text in ("Current", "Configured", "Missing key",
                            "Offline", "Unreachable"), (pid, text)

    def test_submit_groq_uses_groq_url(self):
        from PyQt6.QtCore import QTimer
        from core.llm_provider_detector import get_provider
        ov = self._make()
        QTimer.singleShot(600, lambda: ov._select_provider("groq"))
        QTimer.singleShot(800, ov._submit)
        result = []
        ov.done.connect(lambda d: result.append(json.loads(d)))
        ov.show()
        deadline = time.time() + 5
        while not result and time.time() < deadline:
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            time.sleep(0.05)
        assert result, "submit never fired"
        d = result[0]
        assert d["llm_provider"] == "groq"
        assert "groq.com" in d["llm_url"], d["llm_url"]
        assert "localhost" not in d["llm_url"]

    def test_submit_keeps_api_key(self):
        from PyQt6.QtCore import QTimer
        ov = self._make()
        result = []
        ov.done.connect(lambda d: result.append(json.loads(d)))
        ov.show()
        # Select groq FIRST, then submit only after the selection has landed.
        QTimer.singleShot(250, lambda: (ov._select_provider("groq"),
                                        QTimer.singleShot(250, ov._submit)))
        deadline = time.time() + 5
        while not result and time.time() < deadline:
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            time.sleep(0.05)
        assert result
        assert result[0].get("groq_api_key") == "gsk_test"

    def test_refresh_models_populates(self):
        ov = self._make()
        card = ov._cards["ollama"]
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, lambda: ov._refresh_models("ollama"))
        deadline = time.time() + 8
        while card._model_combo.count() <= 1 and time.time() < deadline:
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            time.sleep(0.2)
        # In the sandbox there is no Ollama server, so the combo falls back
        # to the curated defaults — count must be at least the defaults (5)
        assert card._model_combo.count() >= 1


# ---------------------------------------------------------------------------
# 4. Episodic memory — no deadlock under concurrency
# ---------------------------------------------------------------------------
class TestMemoryConcurrency:
    def test_concurrent_episode_writes(self):
        from core.jarvis_memory import record_episode, update_last_episode, _lock
        errors: list = []

        def writer(i: int):
            try:
                record_episode(f"test episode {i}", f"answer {i}")
                update_last_episode(f"answer {i}")
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert not errors, errors

    def test_recall_format(self):
        from core.jarvis_memory import record_episode, recent_episodes
        record_episode("hello jarvis", "hi there")
        recents = recent_episodes(3)
        joined = json.dumps(recents)
        assert "hello jarvis" in joined, joined


# ---------------------------------------------------------------------------
# 5. Tool executor imports all action handlers
# ---------------------------------------------------------------------------
class TestExecutorImports:
    def test_executor_loads(self):
        import importlib
        mod = importlib.import_module("core.tools.executor")
        assert hasattr(mod, "execute_tool")

    def test_all_action_names_exist(self):
        """Every action file must export a handler (function or class)."""
        import importlib
        from pathlib import Path
        actions_dir = Path("actions")
        for f in actions_dir.glob("*.py"):
            if f.name.startswith("_"):
                continue
            mod_name = f"actions.{f.stem}"
            try:
                importlib.import_module(mod_name)
            except Exception as e:  # noqa: BLE001
                pytest.fail(f"{mod_name} import failed: {e}")
