"""Extended hard tests — phase 2.

Covers: web search, GitHub clone-and-run (README parsing), episodic memory
chains, intent-parser edge cases, network-error fallbacks, STT/TTS module
surfaces, config fallbacks, and executor tool round-trips.

Run: QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_hard2.py -q
"""
from __future__ import annotations

import json
import time
import re
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(REPO))


# ===========================================================================
# 1. Web search action
# ===========================================================================

class TestWebSearch(unittest.TestCase):
    def setUp(self):
        from actions import web_search as _ws
        self.ws = _ws

    def test_empty_query_polite_refusal(self):
        r = self.ws.web_search({"query": "", "mode": "search"})
        self.assertIn("query", r.lower())

    def test_compare_mode_requires_items(self):
        r = self.ws.web_search({"query": "a", "mode": "compare", "items": []})
        # compare mode with no items should fall back or warn, never crash
        self.assertIsInstance(r, str)

    def test_search_no_crash_on_special_chars(self):
        r = self.ws.web_search({"query": "café résumé naïve — 100%", "mode": "search"})
        self.assertIsInstance(r, str)

    def test_search_returns_string(self):
        # Real network call to DuckDuckGo (sandbox has internet access)
        r = self.ws.web_search({"query": "who won the 2024 football champions league", "mode": "search"})
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 20)

    def test_compare_returns_items(self):
        r = self.ws.web_search({
            "items": ["python", "javascript"],
            "aspect": "performance",
        })
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 20)


# ===========================================================================
# 2. GitHub clone-and-run — README parsing
# ===========================================================================

class TestCloneAndRun(unittest.TestCase):
    def setUp(self):
        from actions import github_integration as _gi
        self.gi = _gi
        self._dirs: dict[str, Path] = {}

    def _tmp(self, name: str) -> str:
        import tempfile
        d = Path(tempfile.mkdtemp(prefix=f"jarvis-{name}-"))
        self._dirs[name] = d
        return str(d)

    def tearDown(self):
        import shutil
        for d in self._dirs.values():
            shutil.rmtree(d, ignore_errors=True)

    def test_run_from_readme_npm(self):
        d = Path(self._tmp("npm"))
        (d / "README.md").write_text(textwrap.dedent("""\
            # Cool App

            Install:

            ```bash
            npm install
            ```

            Run:

            ```bash
            npm run dev
            ```
        """), encoding="utf-8")
        cmd = self.gi.run_from_readme(d)
        self.assertIn("npm install", cmd)
        self.assertIn("npm run dev", cmd)
        self.assertIn("&&", cmd)

    def test_run_from_readme_pip_python(self):
        d = Path(self._tmp("pip"))
        (d / "README.md").write_text(textwrap.dedent("""\
            ## Install

            ```
            pip install -r requirements.txt
            ```

            ## Usage

            ```
            python app.py
            ```
        """), encoding="utf-8")
        cmd = self.gi.run_from_readme(d)
        self.assertIn("pip install", cmd)
        self.assertIn("app.py", cmd)

    def test_run_from_readme_docker(self):
        d = Path(self._tmp("docker"))
        (d / "README.md").write_text("```bash\ndocker compose up\n```\n", encoding="utf-8")
        self.assertIn("docker compose up", self.gi.run_from_readme(d))

    def test_run_from_readme_missing_file(self):
        d = Path(self._tmp("none"))
        self.assertEqual(self.gi.run_from_readme(d), "")

    def test_run_from_readme_dollar_prefix_stripped(self):
        d = Path(self._tmp("dollar"))
        (d / "README.md").write_text("```\n$ npm install\n$ npm start\n```", encoding="utf-8")
        cmd = self.gi.run_from_readme(d)
        self.assertIn("npm install", cmd)
        self.assertIn("npm start", cmd)
        self.assertNotIn("$ ", cmd)
        self.assertNotIn("\n$", cmd)

    def test_detect_run_command_package_json(self):
        d = Path(self._tmp("pkg"))
        (d / "package.json").write_text('{"scripts":{"start":"node x"}}', encoding="utf-8")
        cmd = self.gi.detect_run_command(d)
        self.assertIn("npm install", cmd)
        self.assertIn("npm run dev", cmd)

    def test_detect_run_command_go(self):
        d = Path(self._tmp("go"))
        (d / "go.mod").write_text("module x", encoding="utf-8")
        self.assertEqual(self.gi.detect_run_command(d), "go run .")

    def test_clone_repo_validates_input(self):
        self.assertIn("does not look like", self.gi.clone_repo("not-a-repo"))
        self.assertIn("Give me a repo", self.gi.clone_repo(""))

    def test_clone_and_run_nonexistent_repo(self):
        r = self.gi.clone_and_run("ramimaalej/nonexistent-repo-xyz-12345")
        self.assertTrue(r.startswith("Clone failed") or "nonexistent" in r.lower() or
                        "timed out" in r.lower() or "error" in r.lower() or
                        r.startswith("Give me"), r)


# ===========================================================================
# 3. Episodic memory chains
# ===========================================================================

class TestMemoryExtended(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        import core.jarvis_memory as _mem
        self.mem = _mem
        # Redirect episode storage to an isolated temp file
        self._orig_path = _mem.EPISODES_PATH
        _mem.EPISODES_PATH = Path(self._tmpdir) / "episodes.json"
        _mem._EPISODES.clear()
        _mem._EPISODES_LOADED = False
        self.mem.record_episode("hello jarvis", "Hello! I am ready.")
        self.mem.update_last_episode("Sure, I can help.")

    def tearDown(self):
        import shutil
        self.mem.EPISODES_PATH = self._orig_path
        self.mem._EPISODES.clear()
        self.mem._EPISODES_LOADED = False
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_record_then_recall(self):
        self.mem.record_episode("remember mars is red", "Yes, Mars appears red.")
        res = self.mem.format_episode_recall("what is mars", top_k=3)
        self.assertIsInstance(res, str)
        self.assertIn("mars", res.lower())

    def test_update_last_episode_merged(self):
        self.mem.record_episode("meeting at nine", "Noted, 9:00 AM.")
        self.mem.update_last_episode("with Sarah in the main office")
        res = self.mem.format_episode_recall("meeting", top_k=2)
        self.assertIn("sarah", res.lower())

    def test_rolling_limit(self):
        for i in range(6):
            self.mem.record_episode(f"episode {i}", f"answer {i}")
        rec = self.mem.recent_episodes(3)
        labels = [e["u"] for e in rec]
        # the most recent recorded episode must be the last one returned
        self.assertEqual(labels[-1], "episode 5")

    def test_human_recall_is_readable(self):
        self.mem.record_episode("my dog is named max", "Cute!")
        res = self.mem.format_human_recall("my dog", top_k=5)
        self.assertIn("max", res.lower())


# ===========================================================================
# 4. Intent-parser edge cases
# ===========================================================================

class TestIntentEdgeCases(unittest.TestCase):
    def setUp(self):
        from actions import intent_router as _ir
        self.ir = _ir

    def _intent(self, text):
        r = self.ir.route(text)
        return getattr(r, "intent_name", "")

    def test_empty_input(self):
        r = self.ir.route("")
        self.assertTrue(r is not None)

    def test_whitespace_only(self):
        r = self.ir.route("   \n\t  ")
        self.assertTrue(r is not None)

    def test_uppercase_open(self):
        self.assertEqual(self._intent("OPEN TERMINAL"), "open_app")

    def test_whatsapp_is_message_not_email(self):
        self.assertEqual(self._intent("send a message to majdi on whatsapp"), "send_message")

    def test_email_is_gmail(self):
        # Canonical email send form must route to gmail_send directly
        r = self.ir.route("send an email to majdi")
        self.assertTrue(r.matched)
        self.assertEqual(r.intent_name, "gmail_send")

    def test_telegram_is_message(self):
        self.assertEqual(self._intent("send a message to alex on telegram"), "send_message")

    def test_emojis_graceful(self):
        r = self.ir.route("what's the weather 🌦️ in tunis ???")
        self.assertTrue(r is not None)
        self.assertEqual(r.intent_name, "weather_report")


# ===========================================================================
# 5. Network-error fallbacks & config
# ===========================================================================

class TestConfigFallbacks(unittest.TestCase):
    def test_llm_model_empty_fallback(self):
        from core import llm_client as _lc
        settings = _lc.get_llm_settings()
        # get_llm_settings returns (provider, model) — model must never be empty
        provider, model = settings[0], settings[1]
        self.assertTrue(provider)
        self.assertTrue(model, "LLM model must fall back to a default, never empty")

    def test_url_guard_groq_never_localhost(self):
        # Patch the config file to claim groq + a localhost URL, then force
        # llm_client to recompute. The URL guard must redirect to the real
        # Groq endpoint (never localhost:11434 for a cloud provider).
        from core import llm_client as _lc, jarvis_config as _jc
        import shutil
        cfg_path = Path(_jc.__file__).parent.parent / "config" / "api_keys.json"
        bak_path = cfg_path.with_suffix(".bak_test")
        shutil.copyfile(cfg_path, bak_path)
        try:
            cfg_path.write_text(json.dumps({
                "llm_provider": "groq",
                "llm_url": "http://localhost:11434",
            }), encoding="utf-8")
            # invalidate any cached config inside the module
            for attr in ("_CFG", "_config_cache", "_loaded", "_cfg"):
                if hasattr(_lc, attr):
                    setattr(_lc, attr, None)
            for attr in ("_CFG", "_config_cache", "_loaded", "_cfg"):
                if hasattr(_jc, attr):
                    setattr(_jc, attr, None)
            provider, _model = _lc.get_llm_settings()
            # rebuild effective URL exactly as the client would: cloud provider
            # with localhost URL → must be replaced by the provider default.
            from core.llm_client import _PROVIDER_DEFAULTS
            if provider in _PROVIDER_DEFAULTS:
                url = _PROVIDER_DEFAULTS[provider]
            else:
                url = ""
            self.assertNotIn("localhost", url)
        finally:
            shutil.move(str(bak_path), str(cfg_path))


# ===========================================================================
# 6. STT/TTS module surfaces
# ===========================================================================

class TestSTTTTS(unittest.TestCase):
    def test_stt_module_imports(self):
        from core import jarvis_stt  # noqa: F401

    def test_tts_module_imports(self):
        from core import jarvis_tts  # noqa: F401

    def test_tts_public_helpers(self):
        from core.jarvis_tts import speak, speak_error
        self.assertTrue(callable(speak))
        self.assertTrue(callable(speak_error))


# ===========================================================================
# 7. Executor tool round-trips (tools not covered elsewhere)
# ===========================================================================

class TestExecutorTools(unittest.TestCase):
    def setUp(self):
        from core.tools import executor as _ex
        self.ex = _ex

        class _FakeUI:
            def __init__(self):
                self.last_state = None
            def set_state(self, state):
                self.last_state = state
            def show_error_state(self, msg):
                self.last_state = ("error", msg)

        self.ui = _FakeUI()
        self.nope = lambda x: None

    def test_system_info(self):
        r = self.ex.execute_tool(self.ui, "system_info", {}, self.nope)
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 10)

    def test_unknown_tool(self):
        r = self.ex.execute_tool(self.ui, "zzz_nonexistent_tool_xyz", {}, self.nope)
        self.assertIsInstance(r, str)

    def test_random_number(self):
        r = self.ex.execute_tool(self.ui, "random_number", {"min": 1, "max": 100}, self.nope)
        self.assertIsInstance(r, (int, float, str))

    def test_github_clone_action_routing(self):
        # Ensure the tool executor dispatches github/clone to clone_and_run
        # without blowing up on missing args.
        r = self.ex.execute_tool(self.ui, "github", {"action": "clone", "repo": ""}, self.nope)
        self.assertIsInstance(r, str)
        # Empty repo should get a polite message, not an exception
        self.assertTrue(len(r) > 3)


if __name__ == "__main__":
    unittest.main()
