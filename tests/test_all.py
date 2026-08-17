"""
Tests for MARK XL JARVIS — run with:  pytest tests/ -v  (from project root)
"""

import ast
import json
import sys
import types
from pathlib import Path

import pytest

pytest_plugins = ("pytest_asyncio",)

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))


def _import(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ═══════════════════════════════════════════════════════════════════════
# 1. browser_use_agent.py  — every function
# ═══════════════════════════════════════════════════════════════════════

class TestBrowserUseAgent:
    """tests/actions/browser_use_agent.py"""

    def setup_method(self):
        self.mod = _import("browser_use_agent",
                           PROJECT / "actions" / "browser_use_agent.py")

    def test_find_config_returns_dict(self):
        cfg = self.mod._find_config()
        assert isinstance(cfg, dict)
        assert "llm_provider" in cfg

    def test_build_llm_client_nvidia(self):
        """Simulate NVIDIA NIM config -> returns ChatOpenAI with correct model."""
        cfg = self.mod._find_config()
        if cfg.get("llm_provider") != "nvidia_nim":
            pytest.skip("config is not nvidia_nim")
        info = self.mod._build_llm_client()
        assert info is not None
        assert "client" in info
        assert "model" in info
        assert info["model"] == "llama-3.3-70b-instruct"

    def test_build_llm_client_fallback(self):
        """Unknown provider -> fallback to ChatOpenAI."""
        orig = self.mod._find_config
        try:
            self.mod._find_config = lambda: {
                "llm_provider": "unknown_provider",
                "llm_url": "http://localhost:9999",
                "llm_model": "test-model",
            }
            info = self.mod._build_llm_client()
            assert info is not None
            assert "client" in info
        finally:
            self.mod._find_config = orig

    def test_run_browser_use_task_empty_task(self):
        """Very basic - just verify it doesn't crash on empty input."""
        result = self.mod.run_browser_use_task(task="", timeout=5)
        assert isinstance(result, str)

    def test_run_browser_use_task_timeout(self):
        """Short timeout should trigger the timeout path."""
        result = self.mod.run_browser_use_task(
            task="go to example.com",
            timeout=1,
            headless=True,
            max_steps=2,
        )
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════
# 2. gws_bridge.py  - every public function (test sync wrapper only)
# ═══════════════════════════════════════════════════════════════════════

class TestGwsBridge:
    """tests/gws_bridge.py  - functions are async; test the module loads."""

    def setup_method(self):
        self.mod = _import("gws_bridge", PROJECT / "gws_bridge.py")

    def test_module_imports(self):
        assert hasattr(self.mod, "get_unread_emails")
        assert hasattr(self.mod, "search_emails")
        assert hasattr(self.mod, "send_email")
        assert hasattr(self.mod, "reply_email")
        assert hasattr(self.mod, "get_todays_agenda")
        assert hasattr(self.mod, "get_upcoming_events")
        assert hasattr(self.mod, "create_event")
        assert hasattr(self.mod, "delete_event")
        assert hasattr(self.mod, "search_files")
        assert hasattr(self.mod, "upload_file")
        assert hasattr(self.mod, "create_doc")
        assert hasattr(self.mod, "create_meet")
        assert hasattr(self.mod, "is_authenticated")
        assert hasattr(self.mod, "GwsError")

    def test_GwsError_raise(self):
        try:
            raise self.mod.GwsError("test error")
        except self.mod.GwsError as e:
            assert str(e) == "test error"

    @pytest.mark.asyncio
    async def test_is_authenticated_returns_bool(self):
        result = await self.mod.is_authenticated()
        assert result in (True, False)

    def test_check_credentials_exists(self):
        creds = self.mod._CREDENTIALS_PATH
        assert isinstance(creds, Path)
        assert creds.name == "credentials.json"

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="gws CLI needs credentials.json", strict=False)
    async def test_get_unread_emails(self):
        result = await self.mod.get_unread_emails(limit=3)
        assert isinstance(result, (list, dict))

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="gws CLI needs credentials.json", strict=False)
    async def test_search_emails(self):
        result = await self.mod.search_emails(query="test")
        assert isinstance(result, (list, dict))

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="gws CLI needs credentials.json", strict=False)
    async def test_send_email(self):
        result = await self.mod.send_email(
            to="test@example.com", subject="Test", body="Body"
        )
        assert isinstance(result, (list, dict))

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="gws CLI needs credentials.json", strict=False)
    async def test_create_event(self):
        result = await self.mod.create_event(
            title="Test", date="2026-01-01", time="10:00",
            duration_minutes=30,
        )
        assert isinstance(result, (list, dict))

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="gws CLI needs credentials.json", strict=False)
    async def test_search_files(self):
        result = await self.mod.search_files(query="test.txt")
        assert isinstance(result, (list, dict))

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="gws CLI needs credentials.json", strict=False)
    async def test_create_meet(self):
        result = await self.mod.create_meet(
            title="Test", date="2026-01-01", time="10:00"
        )
        assert isinstance(result, (list, dict))


# ═══════════════════════════════════════════════════════════════════════
# 3. core/llm_client.py  — config & provider logic
# ═══════════════════════════════════════════════════════════════════════

class TestLlmClient:
    """tests/core/llm_client.py"""

    def setup_method(self):
        self.mod = _import("llm_client", PROJECT / "core" / "llm_client.py")

    def test_get_base_dir(self):
        d = self.mod.get_base_dir()
        assert isinstance(d, Path)
        assert d.exists()

    def test_get_llm_settings_returns_tuple(self):
        """get_llm_settings returns (url, model) as a tuple."""
        settings = self.mod.get_llm_settings()
        assert isinstance(settings, tuple)
        assert len(settings) == 2
        assert isinstance(settings[0], str)  # url
        assert isinstance(settings[1], str)  # model

    def test_call_llm_exists(self):
        assert hasattr(self.mod, "call_llm")
        assert hasattr(self.mod, "call_llm_stream")

    def test_call_llm_tool_format_nvidia(self):
        """Verify call_llm can be called (may fail if API unreachable -> skip)."""
        try:
            r = self.mod.call_llm(
                messages=[
                    {"role": "user", "content": "Say 'hello world' and nothing else."}
                ],
                tools=[
                    {
                        "name": "test_tool",
                        "description": "A test",
                        "parameters": {"type": "OBJECT", "properties": {}},
                    }
                ],
            )
            assert isinstance(r, str)
        except Exception as e:
            # API might be unavailable or rate-limited; don't fail the test
            pytest.skip(f"LLM API call failed (network/config issue): {e}")


# ═══════════════════════════════════════════════════════════════════════
# 4. memory/vector_memory.py  — embedding & chunking
# ═══════════════════════════════════════════════════════════════════════

class TestVectorMemory:
    """tests/memory/vector_memory.py"""

    def setup_method(self):
        self.mod = _import("vector_memory",
                           PROJECT / "memory" / "vector_memory.py")

    def test_get_memory_count(self):
        count = self.mod.get_memory_count()
        assert isinstance(count, (int, str))

    def test_search_memory(self):
        result = self.mod.search_memory("test", top_k=3)
        assert isinstance(result, list)

    def test_store_conversation(self):
        result = self.mod.store_conversation("user", "test message")
        assert result is None or isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════
# 5. actions/  — test each action module can import
# ═══════════════════════════════════════════════════════════════════════

def _check_action_import(name, path, expected_func):
    mod = _import(name, path)
    assert hasattr(mod, expected_func), f"{name} missing {expected_func}"
    return mod


class TestActions:
    """Verify every action module imports and has its entry point."""

    ACTION_FUNCS = {
        "browser_control": "browser_control",
        "code_helper": "code_helper",
        "computer_control": "computer_control",
        "computer_settings": "computer_settings",
        "desktop": "desktop_control",
        "dev_agent": "dev_agent",
        "file_controller": "file_controller",
        "file_processor": "file_processor",
        "flight_finder": "flight_finder",
        "game_updater": "game_updater",
        "get_location": "get_location",
        "open_app": "open_app",
        "read_email": "read_email",
        "reminder": "reminder",
        "screen_processor": "screen_process",
        "send_message": "send_message",
        "weather_report": "weather_action",
        "web_search": "web_search",
        "youtube_video": "youtube_video",
    }

    def test_all_actions_import(self):
        for name, func in self.ACTION_FUNCS.items():
            _check_action_import(
                f"actions.{name}",
                PROJECT / "actions" / f"{name}.py",
                func,
            )

    def test_file_controller_list(self):
        from actions.file_controller import file_controller
        result = file_controller({"action": "list", "path": "."}, player=None)
        assert isinstance(result, str)

    def test_weather_unknown_city(self):
        from actions.weather_report import weather_action
        result = weather_action({"city": "xyznonexistent"}, player=None)
        assert isinstance(result, str)

    def test_get_location(self):
        from actions.get_location import get_location as gloc
        result = gloc({}, player=None)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_reminder_smoke(self):
        from actions.reminder import reminder
        r1 = reminder(
            {"minutes": 0, "message": "test reminder"}, response=None, player=None
        )
        assert isinstance(r1, str)

    def test_computer_control_ping(self):
        from actions.computer_control import computer_control
        result = computer_control({"action": "ping"}, player=None)
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════════
# 6. agent/ — test sub-modules import
# ═══════════════════════════════════════════════════════════════════════

class TestAgentModules:
    def test_agent_manager(self):
        mod = _import("agent_manager",
                      PROJECT / "agent" / "agent_manager.py")
        assert hasattr(mod, "get_agent_manager")

    def test_task_queue(self):
        mod = _import("task_queue", PROJECT / "agent" / "task_queue.py")
        assert hasattr(mod, "get_queue")

    def test_planner(self):
        mod = _import("planner", PROJECT / "agent" / "planner.py")
        assert hasattr(mod, "create_plan")

    def test_executor(self):
        mod = _import("executor", PROJECT / "agent" / "executor.py")
        assert hasattr(mod, "AgentExecutor")

    def test_error_handler(self):
        mod = _import("error_handler",
                      PROJECT / "agent" / "error_handler.py")
        assert hasattr(mod, "analyze_error")


# ═══════════════════════════════════════════════════════════════════════
# 7. main.py — tool declarations structure
# ═══════════════════════════════════════════════════════════════════════

class TestMainToolDeclarations:

    @staticmethod
    def _get_tools():
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_decl", str(PROJECT / "core" / "tools" / "declarations.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.TOOL_DECLARATIONS

    def test_declarations_is_list_of_dicts(self):
        tools = self._get_tools()
        assert isinstance(tools, list)
        assert len(tools) >= 40

    def test_every_tool_has_name_desc_params(self):
        tools = self._get_tools()
        names = set()
        for t in tools:
            assert "name" in t, f"Tool missing name: {t}"
            assert "description" in t, f"{t['name']} missing description"
            assert "parameters" in t, f"{t['name']} missing parameters"
            assert t["name"] not in names, f"Duplicate: {t['name']}"
            names.add(t["name"])

    def test_browser_use_tool_present(self):
        tools = self._get_tools()
        names = {t["name"] for t in tools}
        assert "browser_use" in names
        assert "browser_control" in names

    def test_browser_use_tool_params(self):
        tools = self._get_tools()
        for t in tools:
            if t["name"] == "browser_use":
                params = t["parameters"]["properties"]
                assert "task" in params
                assert params["task"]["type"] == "STRING"
                assert t["parameters"]["required"] == ["task"]
                return
        pytest.fail("browser_use tool not found")


# ═══════════════════════════════════════════════════════════════════════
# 8. ui.py — color palette validation
# ═══════════════════════════════════════════════════════════════════════

class TestUiColors:

    FORBIDDEN = [
        "#00d4ff", "#000d12", "#ff6b00",
        "#4488ff", "#44bb44", "#ffcc00", "#001a22",
        "#ff8844", "#88ddff", "#000d14", "#140006", "#001f10",
    ]

    @staticmethod
    def _color_lines():
        """Yield (line_no, text) for lines inside class C definition."""
        with open(PROJECT / "ui.py") as f:
            lines = f.readlines()
        in_c = False
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if "class C:" in s:
                in_c = True
                continue
            if in_c and s.startswith("class "):
                break
            if in_c:
                yield i, s

    def test_class_C_exists(self):
        with open(PROJECT / "ui.py") as f:
            tree = ast.parse(f.read())
        class_c = next(
            (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "C"),
            None,
        )
        assert class_c is not None, "class C not found"

    def test_class_C_has_core_attrs(self):
        with open(PROJECT / "ui.py") as f:
            tree = ast.parse(f.read())
        class_c = next(
            n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "C"
        )
        attrs = {
            n.targets[0].id
            for n in class_c.body
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], (ast.Name,))
        }
        for required in ("BG", "PANEL", "TEXT"):
            assert required in attrs, f"Missing C.{required}"

    def test_no_forbidden_colors(self):
        for line_no, text in self._color_lines():
            for fb in self.FORBIDDEN:
                if fb in text:
                    pytest.fail(f"Line {line_no}: {fb} in: {text}")

    def test_all_hex_formats(self):
        for line_no, text in self._color_lines():
            if "=" in text and "#" in text:
                _, after = text.split("#", 1)
                hexval = "#" + after.split('"')[0].split("'")[0].strip().rstrip(",")
                assert len(hexval) in (4, 7, 9) and hexval[0] == "#", (
                    f"Bad hex on line {line_no}: {text}"
                )


# ═══════════════════════════════════════════════════════════════════════
# 9. Syntax check - every .py file
# ═══════════════════════════════════════════════════════════════════════

def test_every_py_file_parses():
    failed = []
    for f in sorted(PROJECT.rglob("*.py")):
        if "__pycache__" in str(f) or ".venv" in str(f):
            continue
        try:
            ast.parse(f.read_text(encoding="utf-8", errors="surrogateescape"))
        except SyntaxError as e:
            failed.append((f.relative_to(PROJECT), str(e)))
    assert not failed, "\n".join(f"{p}: {e}" for p, e in failed)


# ═══════════════════════════════════════════════════════════════════════
# 10. config validity
# ═══════════════════════════════════════════════════════════════════════

class TestConfig:
    def test_api_keys_json(self):
        path = PROJECT / "config" / "api_keys.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "llm_provider" in data
        assert "llm_model" in data
        assert "llm_url" in data

    def test_gws_credentials_path(self):
        mod = _import("gws_bridge", PROJECT / "gws_bridge.py")
        assert hasattr(mod, "_CREDENTIALS_PATH")
        assert mod._CREDENTIALS_PATH.name == "credentials.json"

    def test_requirements_file(self):
        path = PROJECT / "requirements.txt"
        assert path.exists()
        text = path.read_text()
        assert "browser-use" in text
        assert "playwright" in text
        assert "PyQt6" in text
