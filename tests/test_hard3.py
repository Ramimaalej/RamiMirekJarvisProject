"""Hard tests batch 3 — user profile, public APIs, OpenCode, proactive chat.

Run: QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_hard3.py -q
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------------------------------------------------------------------
# User profile
# ---------------------------------------------------------------------------

class TestUserProfile:
    """config/user_profile.json + core/jarvis_profile.py must work offline."""

    def test_profile_file_valid(self):
        path = REPO / "config" / "user_profile.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("name")
        assert data.get("city") or data.get("location")

    def test_profile_loads(self):
        from core.jarvis_profile import load_profile
        prof = load_profile()
        assert isinstance(prof, dict)
        assert prof.get("name")

    def test_profile_for_prompt_not_empty(self):
        from core.jarvis_profile import profile_for_prompt
        ctx = profile_for_prompt()
        assert isinstance(ctx, str)
        assert len(ctx) > 100  # meaningful chunk injected into system prompt

    def test_profile_context_mentions_rami(self):
        from core.jarvis_profile import profile_for_prompt
        ctx = profile_for_prompt().lower()
        assert "rami" in ctx or "maalej" in ctx

    def test_profile_context_not_injected_on_missing_file(self):
        from core import jarvis_profile as _jp
        saved = _jp._profile_path
        try:
            _jp._profile_path = lambda: Path("/tmp/nonexistent_profile_12345.json")
            _jp._cache = None
            from core.jarvis_prompt import _build_system_prompt
            prompt = _build_system_prompt("hello")
            assert isinstance(prompt, str)  # must not crash
        finally:
            _jp._profile_path = saved
            _jp._cache = None


# ---------------------------------------------------------------------------
# Public APIs intents (routing, no network in routing tests)
# ---------------------------------------------------------------------------

class TestPublicApiIntents:
    def test_crypto_routing(self):
        from actions.intent_router import route
        assert route("btc price").intent_name == "check_crypto"
        assert route("ethereum price in eur").intent_name == "check_crypto"
        assert route("how much is bitcoin").intent_name == "check_crypto"

    def test_crypto_no_false_positive(self):
        from actions.intent_router import route
        r = route("tell me a story about bitcoin mining")
        assert r.intent_name != "check_crypto" or r.confidence < 0.3

    def test_currency_routing(self):
        from actions.intent_router import route
        assert route("convert 100 eur to usd").intent_name == "currency_rate"
        assert route("EURUSD rate").intent_name == "currency_rate"

    def test_time_routing(self):
        from actions.intent_router import route
        assert route("what time is it in london").intent_name == "check_time"
        assert route("heure à sfax").intent_name == "check_time"

    def test_quote_routing(self):
        from actions.intent_router import route
        assert route("give me a quote").intent_name == "random_quote"

    def test_opencode_routing(self):
        from actions.intent_router import route
        assert route("execute new dev project").intent_name == "opencode_run"
        assert route("build me a todo app").intent_name == "opencode_run"
        assert route("install opencode").intent_name == "opencode_install"
        assert route("is opencode installed").intent_name == "opencode_status"

    def test_opencode_is_ai_required(self):
        """opencode_run goes through the LLM so it gets a detailed prompt."""
        from actions.intent_router import route
        r = route("build me a todo app")
        assert r.requires_ai is True


# ---------------------------------------------------------------------------
# Public APIs live (real endpoints, timeout-bounded)
# ---------------------------------------------------------------------------

class TestPublicApisLive:
    def test_crypto_live(self):
        from actions.public_apis import check_crypto
        out = check_crypto("bitcoin", "usd")
        assert "bitcoin" in out.lower() or "USD" in out or "up" in out or "down" in out

    def test_rate_live(self):
        from actions.public_apis import check_rate
        out = check_rate("EURUSD")
        assert "=" in out

    def test_time_live(self):
        from actions.public_apis import check_time
        out = check_time("london")
        assert ":" in out  # HH:MM present (online API or local fallback)

    def test_quote_live_or_fallback(self):
        from actions.public_apis import check_quote
        out = check_quote()
        assert '"' in out or "“" in out  # always returns a quote

    def test_time_aliases(self):
        from actions.public_apis import check_time
        out = check_time("sfax")
        assert ":" in out


# ---------------------------------------------------------------------------
# OpenCode integration
# ---------------------------------------------------------------------------

class TestOpenCode:
    def test_module_imports(self):
        from actions import opencode_launcher
        assert hasattr(opencode_launcher, "opencode_action")
        assert hasattr(opencode_launcher, "detect_opencode")
        assert hasattr(opencode_launcher, "build_detailed_prompt")

    def test_detailed_prompt_build(self):
        from actions.opencode_launcher import build_detailed_prompt
        prompt = build_detailed_prompt("build me a todo app with vue.js")
        assert "todo" in prompt.lower()
        assert len(prompt) > 300  # must be a detailed structured prompt

    def test_status_action_no_crash(self):
        from actions.opencode_launcher import opencode_action
        out = opencode_action({"action": "status"})
        assert isinstance(out, str) and len(out) > 3

    def test_install_action_no_sudo(self):
        from actions.opencode_launcher import opencode_action
        out = opencode_action({"action": "install"})
        assert "sudo" not in out.lower() or "password" not in out.lower()

    def test_run_action_empty_dir(self):
        from actions.opencode_launcher import opencode_action
        out = opencode_action({"action": "run", "description": "test", "dir": ""})
        assert isinstance(out, str)


# ---------------------------------------------------------------------------
# Proactive / clarifying conversation policy
# ---------------------------------------------------------------------------

class TestProactivePolicy:
    def test_prompt_allows_clarification(self):
        prompt_path = REPO / "core" / "prompt.txt"
        text = prompt_path.read_text(encoding="utf-8")
        assert "CLARIFY" in text or "ambigu" in text.lower()
        assert "NEVER ask follow-up questions" not in text

    def test_prompt_proactive(self):
        prompt_path = REPO / "core" / "prompt.txt"
        text = prompt_path.read_text(encoding="utf-8")
        assert "proactive" in text.lower() or "suggest" in text.lower()

    def test_tools_in_declarations(self):
        from core.tools.declarations import TOOL_DECLARATIONS
        names = {t["name"] for t in TOOL_DECLARATIONS}
        for n in ("check_crypto", "check_rate", "check_time", "check_quote",
                  "opencode_run", "opencode_install", "opencode_status"):
            assert n in names, f"{n} missing from TOOL_DECLARATIONS"
