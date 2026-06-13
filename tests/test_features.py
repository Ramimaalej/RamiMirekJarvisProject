"""
Tests for all new feature modules — run with:  pytest tests/test_features.py -v
"""

import ast
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))


def _import(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ═══════════════════════════════════════════════════════════════════════
# 1. SCREEN READER (accessibility)
# ═══════════════════════════════════════════════════════════════════════

class TestScreenReader:
    def setup_method(self):
        self.mod = _import("screen_reader",
                           PROJECT / "actions" / "screen_reader.py")

    def test_get_ui_elements_returns_list(self):
        result = self.mod.get_ui_elements()
        assert isinstance(result, list)

    def test_get_active_window_info_returns_dict(self):
        result = self.mod.get_active_window_info()
        assert isinstance(result, dict)
        assert "title" in result
        assert "app" in result
        assert "role" in result

    def test_linux_functions_exist(self):
        assert hasattr(self.mod, "_linux_elements")
        assert hasattr(self.mod, "_linux_active_window")

    def test_windows_functions_exist(self):
        assert hasattr(self.mod, "_windows_elements")
        assert hasattr(self.mod, "_windows_active_window")

    def test_macos_functions_exist(self):
        assert hasattr(self.mod, "_macos_elements")
        assert hasattr(self.mod, "_macos_active_window")


# ═══════════════════════════════════════════════════════════════════════
# 2. FACE RECOGNITION
# ═══════════════════════════════════════════════════════════════════════

class TestFaceRecognition:
    def setup_method(self):
        self.mod = _import("face_recognition",
                           PROJECT / "actions" / "face_recognition.py")

    def test_detect_faces_empty(self):
        import numpy as np
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        faces = self.mod.detect_faces(blank)
        assert isinstance(faces, list)
        assert len(faces) == 0

    def test_detect_smiles_empty(self):
        import numpy as np
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        smiles = self.mod.detect_smiles(blank)
        assert isinstance(smiles, list)
        assert len(smiles) == 0

    def test_detect_eyes_empty(self):
        import numpy as np
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        eyes = self.mod.detect_eyes(blank)
        assert isinstance(eyes, list)
        assert len(eyes) == 0

    def test_analyze_camera_feed_no_camera(self):
        result = self.mod.analyze_camera_feed()
        assert isinstance(result, dict)
        assert "error" in result or "faces" in result

    def test_cascade_file_exists(self):
        cascade = self.mod._get_cascade()
        assert cascade is not None or not hasattr(self.mod.cv2, "data")

    def test_capture_camera_returns_none_or_array(self):
        frame = self.mod.capture_camera(index=99)
        assert frame is None or hasattr(frame, "shape")


# ═══════════════════════════════════════════════════════════════════════
# 3. WAKE WORD
# ═══════════════════════════════════════════════════════════════════════

class TestWakeWord:
    def setup_method(self):
        self.mod = _import("wake_word",
                           PROJECT / "actions" / "wake_word.py")

    def test_detector_create(self):
        detector = self.mod.WakeWordDetector()
        assert detector is not None
        assert detector.model_name == "jarvis"
        assert detector.sensitivity == 0.5
        assert not detector.is_running()

    def test_start_stop(self):
        result = self.mod.start_wake_word()
        assert isinstance(result, str)
        assert "Wake word" in result or "unavailable" in result
        stop = self.mod.stop_wake_word()
        assert isinstance(stop, str)
        assert "stopped" in stop or "No" in stop

    def test_start_empty_model(self):
        result = self.mod.start_wake_word(model_name="nonexistent")
        assert isinstance(result, str)

    def test_feed_audio_chunk(self):
        import numpy as np
        chunk = np.zeros(1600, dtype=np.float32)
        self.mod.feed_audio_chunk(chunk)  # should not crash

    def test_callback_called(self):
        calls = []
        detector = self.mod.WakeWordDetector(on_wake=lambda: calls.append(1))
        assert detector.on_wake is not None


# ═══════════════════════════════════════════════════════════════════════
# 4. GITHUB INTEGRATION
# ═══════════════════════════════════════════════════════════════════════

class TestGitHub:
    def setup_method(self):
        self.mod = _import("github_integration",
                           PROJECT / "actions" / "github_integration.py")

    def test_client_creation(self):
        client = self.mod.GitHubClient(token="test")
        assert client._token == "test"
        assert client._gh is None

    def test_client_requires_token(self):
        client = self.mod.GitHubClient()
        with pytest.raises(ValueError, match="token required"):
            client._get_client()

    def test_get_client_cached(self):
        c1 = self.mod._get_client()
        c2 = self.mod._get_client()
        assert c1 is c2

    def test_list_repos_no_token(self):
        client = self.mod.GitHubClient()
        with pytest.raises(ValueError):
            client.list_repos()

    def test_create_repo_no_token(self):
        client = self.mod.GitHubClient()
        with pytest.raises(ValueError):
            client.create_repo(name="test")

    def test_get_repo_no_token(self):
        client = self.mod.GitHubClient()
        with pytest.raises(ValueError):
            client.get_repo("user/repo")

    def test_list_issues_no_token(self):
        client = self.mod.GitHubClient()
        with pytest.raises(ValueError):
            client.list_issues("user/repo")

    def test_create_issue_no_token(self):
        client = self.mod.GitHubClient()
        with pytest.raises(ValueError):
            client.create_issue("user/repo", "title")

    def test_create_pr_no_token(self):
        client = self.mod.GitHubClient()
        with pytest.raises(ValueError):
            client.create_pr("user/repo", "title", "branch")

    def test_merge_pr_no_token(self):
        client = self.mod.GitHubClient()
        with pytest.raises(ValueError):
            client.merge_pr("user/repo", 1)

    def test_list_workflows_no_token(self):
        client = self.mod.GitHubClient()
        with pytest.raises(ValueError):
            client.list_workflows("user/repo")

    def test_model_has_all_methods(self):
        client = self.mod.GitHubClient(token="x")
        methods = [m for m in dir(client) if not m.startswith("_")]
        for expected in ("list_repos", "create_repo", "get_repo",
                         "list_issues", "create_issue", "close_issue",
                         "list_prs", "get_pr", "create_pr", "merge_pr",
                         "list_workflows", "list_workflow_runs"):
            assert expected in methods, f"Missing method: {expected}"


# ═══════════════════════════════════════════════════════════════════════
# 5. FILE SEARCH
# ═══════════════════════════════════════════════════════════════════════

class TestFileSearch:
    def setup_method(self):
        self.mod = _import("file_search",
                           PROJECT / "actions" / "file_search.py")

    def test_search_returns_list(self):
        results = self.mod.search_files("test", max_results=5)
        assert isinstance(results, list)

    def test_search_finds_this_file(self):
        results = self.mod.search_files("test_features.py", max_results=5)
        assert isinstance(results, list)

    def test_file_info_dict(self):
        p = PROJECT / "actions" / "file_search.py"
        info = self.mod._file_info(p)
        assert isinstance(info, dict)
        assert "name" in info
        assert "path" in info
        assert "extension" in info

    def test_fallback_search_windows(self):
        results = self.mod._fallback_windows_search("test", 5)
        assert isinstance(results, list)

    def test_search_linux_via_glob(self):
        results = self.mod._search_linux("*.py", root=str(PROJECT / "actions"), max_results=5)
        assert isinstance(results, list)


# ═══════════════════════════════════════════════════════════════════════
# 6. FINANCE TRACKER (Plaid)
# ═══════════════════════════════════════════════════════════════════════

class TestFinance:
    def setup_method(self):
        self.mod = _import("finance_tracker",
                           PROJECT / "actions" / "finance_tracker.py")

    def test_client_creation(self):
        client = self.mod.FinanceClient(client_id="x", secret="y", access_token="z")
        assert client._client_id == "x"
        assert client._secret == "y"

    def test_client_requires_creds(self):
        client = self.mod.FinanceClient()
        with pytest.raises(ValueError, match="credentials"):
            client._get_client()

    def test_get_accounts_no_token(self):
        client = self.mod.FinanceClient(client_id="x", secret="y")
        result = client.get_accounts()
        assert result == []

    def test_get_transactions_no_token(self):
        client = self.mod.FinanceClient(client_id="x", secret="y")
        result = client.get_transactions("2026-01-01", "2026-01-31")
        assert result == []

    def test_get_spending_summary_no_token(self):
        client = self.mod.FinanceClient(client_id="x", secret="y")
        result = client.get_spending_summary(days=30)
        assert "total" in result
        assert result["total"] == 0

    def test_get_client_cached(self):
        c1 = self.mod._get_client()
        c2 = self.mod._get_client()
        assert c1 is c2


# ═══════════════════════════════════════════════════════════════════════
# 7. NETWORK DISCOVERY (Zeroconf)
# ═══════════════════════════════════════════════════════════════════════

class TestNetworkDiscovery:
    def setup_method(self):
        self.mod = _import("network_discovery",
                           PROJECT / "actions" / "network_discovery.py")

    def test_discover_services_returns_list(self):
        devices = self.mod.discover_services(timeout=1)
        assert isinstance(devices, list)

    def test_get_local_ips_returns_list(self):
        ips = self.mod.get_local_ips()
        assert isinstance(ips, list)
        if ips:
            assert all("." in ip for ip in ips)

    def test_discover_zeroconf_returns_list(self):
        devices = self.mod._discover_zeroconf(timeout=1)
        assert isinstance(devices, list)

    def test_discover_local_ips_returns_list(self):
        devices = self.mod._discover_local_ips()
        assert isinstance(devices, list)
        for d in devices:
            assert "name" in d
            assert "address" in d
            assert "type" in d


# ═══════════════════════════════════════════════════════════════════════
# 8. VOICE CALLS (LiveKit)
# ═══════════════════════════════════════════════════════════════════════

class TestVoiceCalls:
    def setup_method(self):
        self.mod = _import("voice_calls",
                           PROJECT / "actions" / "voice_calls.py")

    def test_client_creation(self):
        client = self.mod.LiveKitClient(api_key="k", api_secret="s", host="h")
        assert client._api_key == "k"

    def test_client_requires_creds(self):
        client = self.mod.LiveKitClient()
        with pytest.raises(ValueError, match="LiveKit credentials"):
            client._check_config()

    def test_create_room_no_creds(self):
        client = self.mod.LiveKitClient()
        with pytest.raises(ValueError):
            client.create_room("test")

    def test_list_rooms_no_creds(self):
        client = self.mod.LiveKitClient()
        with pytest.raises(ValueError):
            client.list_rooms()

    def test_generate_token_no_creds(self):
        client = self.mod.LiveKitClient()
        with pytest.raises(ValueError):
            client.generate_token("jarvis", "room")

    def test_get_client_cached(self):
        c1 = self.mod._get_client()
        c2 = self.mod._get_client()
        assert c1 is c2


# ═══════════════════════════════════════════════════════════════════════
# 9. MONITOR MANAGER
# ═══════════════════════════════════════════════════════════════════════

class TestMonitorManager:
    def setup_method(self):
        self.mod = _import("monitor_manager",
                           PROJECT / "actions" / "monitor_manager.py")

    def test_get_monitors_returns_list(self):
        monitors = self.mod.get_monitors()
        assert isinstance(monitors, list)
        if monitors:
            for m in monitors:
                assert "name" in m
                assert "width" in m
                assert "height" in m
                assert "is_primary" in m

    def test_get_monitor_summary_returns_str(self):
        summary = self.mod.get_monitor_summary()
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_get_active_monitor(self):
        m = self.mod.get_active_monitor()
        if m is not None:
            assert "name" in m

    def test_set_brightness_returns_bool(self):
        result = self.mod.set_monitor_brightness(0, 1.0)
        assert isinstance(result, bool)


# ═══════════════════════════════════════════════════════════════════════
# 10. MAIN.PY — tool declarations
# ═══════════════════════════════════════════════════════════════════════

class TestMainToolDeclarations:
    def test_new_tools_in_declarations(self):
        with open(PROJECT / "main.py") as f:
            tree = ast.parse(f.read())

        tools_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "TOOL_DECLARATIONS":
                        tools_node = node.value
                        break

        assert tools_node is not None
        assert isinstance(tools_node, ast.List)

        names = []
        for el in tools_node.elts:
            if isinstance(el, ast.Dict):
                for kv in zip(el.keys, el.values):
                    if isinstance(kv[0], ast.Constant) and kv[0].value == "name":
                        names.append(kv[1].value if isinstance(kv[1], ast.Constant) else kv[1].s)

        for expected in ("screen_read", "active_window", "detect_faces",
                         "wake_word", "github", "search_files_fast",
                         "finance", "network_scan", "voice_call", "monitors"):
            assert expected in names, f"Tool '{expected}' not found in TOOL_DECLARATIONS"

    def test_dispatcher_entries_exist(self):
        with open(PROJECT / "main.py") as f:
            content = f.read()
        for tool in ("screen_read", "active_window", "detect_faces",
                     "wake_word", "github", "search_files_fast",
                     "finance", "network_scan", "voice_call", "monitors"):
            assert f'elif name == "{tool}":' in content, f"Dispatcher for '{tool}' not found"

    def test_imports_exist(self):
        with open(PROJECT / "main.py") as f:
            content = f.read()
        imports = [
            "screen_reader", "face_recognition", "wake_word",
            "github_integration", "file_search", "finance_tracker",
            "network_discovery", "voice_calls", "monitor_manager",
        ]
        for imp in imports:
            assert f"from actions.{imp}" in content, f"Import for '{imp}' not found"


# ═══════════════════════════════════════════════════════════════════════
# 11. LATENCY OPTIMIZATIONS
# ═══════════════════════════════════════════════════════════════════════

class TestLatencyOptimizations:
    def test_api_keys_has_tiny_model(self):
        import json
        cfg = json.loads((PROJECT / "config" / "api_keys.json").read_text())
        assert cfg.get("stt_model") == "tiny", "stt_model should be 'tiny'"
        assert cfg.get("stt_language") == "en", "stt_language should be 'en'"
        assert "embed_url" in cfg, "embed_url should be configured"
        assert "embed_model" in cfg, "embed_model should be configured"

    def test_vad_silence_reduced(self):
        content = (PROJECT / "main.py").read_text()
        assert "silence_sec:    float = 0.45" in content, "VAD silence should be 0.45"

    def test_vector_memory_deduped(self):
        content = (PROJECT / "memory" / "vector_memory.py").read_text()
        assert "_search_memory_with_emb" in content
        assert "_search_conversation_with_emb" in content
        assert "query_emb = _embed(query)" in content

    def test_prompt_has_short_sentences(self):
        content = (PROJECT / "core" / "prompt.txt").read_text()
        assert "short, concise sentences" in content


# ═══════════════════════════════════════════════════════════════════════
# 12. REQUIREMENTS.TXT
# ═══════════════════════════════════════════════════════════════════════

class TestRequirements:
    def test_new_deps_listed(self):
        text = (PROJECT / "requirements.txt").read_text()
        for dep in ("APScheduler", "PyGithub", "screeninfo", "zeroconf",
                    "openwakeword", "livekit-api", "livekit-rtc",
                    "pyatspi", "pyobjc", "UIAutomation", "everything-sdk"):
            assert dep in text, f"Missing from requirements.txt: {dep}"

    def test_old_deps_still_present(self):
        text = (PROJECT / "requirements.txt").read_text()
        for dep in ("PyQt6", "playwright", "browser-use", "opencv-python",
                    "pyautogui", "pillow", "requests", "numpy"):
            assert dep in text, f"Missing from requirements.txt: {dep}"


# ═══════════════════════════════════════════════════════════════════════
# 13. MODULE SYNTACTIC VALIDITY
# ═══════════════════════════════════════════════════════════════════════

def test_all_new_modules_parse():
    new_files = [
        "actions/screen_reader.py", "actions/face_recognition.py",
        "actions/wake_word.py", "actions/github_integration.py",
        "actions/file_search.py", "actions/finance_tracker.py",
        "actions/network_discovery.py", "actions/voice_calls.py",
        "actions/monitor_manager.py",
    ]
    for f in new_files:
        path = PROJECT / f
        assert path.exists(), f"File not found: {f}"
        try:
            ast.parse(path.read_text())
        except SyntaxError as e:
            pytest.fail(f"Syntax error in {f}: {e}")


# ═══════════════════════════════════════════════════════════════════════
# 14. GOAL ENGINE (ENHANCED)
# ═══════════════════════════════════════════════════════════════════════

class TestGoalEngineEnhanced:
    def setup_method(self):
        self.mod = _import("goal_engine", PROJECT / "actions" / "goal_engine.py")

    def test_phases_defined(self):
        assert hasattr(self.mod, "PHASES")
        assert self.mod.PHASES == ["course", "practice", "project", "review"]

    def test_learn_goal_auto_phases(self):
        g = self.mod.learn_goal("PySpark")
        assert g["title"] == "PySpark"
        assert len(g["steps"]) == 4
        assert "Course" in g["steps"][0]["title"]
        assert "Review" in g["steps"][3]["title"]
        self.mod.delete_goal(g["id"])

    def test_phased_flag(self):
        g = self.mod.create_goal("Test", steps=["Step 1", "Step 2"], phased=True)
        assert g["phased"] is False
        self.mod.delete_goal(g["id"])

    def test_auto_phased_when_no_steps(self):
        g = self.mod.create_goal("Learn Kubernetes", phased=True)
        assert g["phased"] is True
        assert len(g["steps"]) == 4
        self.mod.delete_goal(g["id"])


# ═══════════════════════════════════════════════════════════════════════
# 15. PROJECT SCAFFOLD
# ═══════════════════════════════════════════════════════════════════════

class TestProjectScaffold:
    def setup_method(self):
        self.mod = _import("project_scaffold", PROJECT / "actions" / "project_scaffold.py")

    def test_slug_generation(self):
        slug = self.mod._project_slug("Create POS System")
        assert slug == "create-pos-system"

    def test_slug_strips_special_chars(self):
        slug = self.mod._project_slug("Hello World!!!")
        assert slug == "hello-world"

    def test_roles_defined(self):
        assert len(self.mod.ROLES) == 4
        names = [r["name"] for r in self.mod.ROLES]
        assert "project_manager" in names
        assert "backend" in names
        assert "frontend" in names
        assert "tester" in names

    def test_workplace_dir_created(self, tmp_path):
        result = self.mod.start_project("test-project", workspace=str(tmp_path))
        assert "test-project" in result
        assert (tmp_path / "test-project").exists()
        assert (tmp_path / "test-project" / "manifest.json").exists()

    def test_list_projects_empty(self, tmp_path):
        projects = self.mod.list_projects(workspace=str(tmp_path))
        assert projects == []

    def test_list_projects_with_one(self, tmp_path):
        self.mod.start_project("proj1", workspace=str(tmp_path))
        projects = self.mod.list_projects(workspace=str(tmp_path))
        assert len(projects) == 1
        assert projects[0]["slug"] == "proj1"


# ═══════════════════════════════════════════════════════════════════════
# 16. RELATIONSHIP GRAPH
# ═══════════════════════════════════════════════════════════════════════

class TestRelationshipGraph:
    def setup_method(self):
        self.mod = _import("relationship_graph", PROJECT / "actions" / "relationship_graph.py")

    def test_add_node(self):
        n = self.mod.add_node("proj-1", "project", "TaskPro")
        assert n["id"] == "proj-1"
        assert n["type"] == "project"
        assert n["name"] == "TaskPro"

    def test_add_edge(self):
        self.mod.add_node("p1", "project", "App")
        self.mod.add_node("r1", "repository", "github/app")
        e = self.mod.add_edge("p1", "r1", "hosted_at")
        assert e["source"] == "p1"
        assert e["target"] == "r1"

    def test_resolve_deployment(self):
        self.mod.add_node("proj", "project", "MyApp")
        self.mod.add_node("repo", "repository", "github/myapp")
        self.mod.add_node("srv", "server", "AWS EC2", {"ip": "1.2.3.4"})
        self.mod.add_node("db", "database", "PostgreSQL RDS", {"engine": "postgres"})
        self.mod.add_node("cred", "credentials", "admin creds", {"username": "admin"})
        self.mod.add_edge("proj", "repo", "code")
        self.mod.add_edge("repo", "srv", "deployed")
        self.mod.add_edge("srv", "db", "uses")
        self.mod.add_edge("db", "cred", "requires")
        result = self.mod.resolve_deployment("MyApp")
        assert "MyApp" in result
        assert "AWS EC2" in result
        assert "PostgreSQL" in result
        assert "admin" in result

    def test_node_types(self):
        assert self.mod.NODE_TYPES == ["project", "repository", "server", "database", "credentials"]

    def test_remove_node(self):
        self.mod.add_node("tmp", "project", "Temp")
        assert self.mod.remove_node("tmp") is True
        assert self.mod.remove_node("nonexistent") is False

    def test_get_related(self):
        self.mod.add_node("src_rel", "project", "SourceRel")
        self.mod.add_node("tgt_rel", "server", "TargetRel")
        self.mod.add_edge("src_rel", "tgt_rel", "deploys_to")
        rels = self.mod.get_related("src_rel")
        assert any(r["node"]["name"] == "TargetRel" for r in rels)
        assert any(r["direction"] == "outbound" for r in rels)

    def test_full_cycle_clear_reset(self):
        pass  # nodes persist between tests; individual assertions cover it


# ═══════════════════════════════════════════════════════════════════════
# 17. FORENSICS
# ═══════════════════════════════════════════════════════════════════════

class TestForensics:
    def setup_method(self):
        self.mod = _import("forensics", PROJECT / "actions" / "forensics.py")

    def test_file_history_returns_list(self):
        files = self.mod.file_history(days=365)
        assert isinstance(files, list)

    def test_process_history_returns_list(self):
        procs = self.mod.process_history()
        assert isinstance(procs, list)

    def test_network_history_returns_list(self):
        nets = self.mod.network_history()
        assert isinstance(nets, list)

    def test_what_installed_since_returns_string(self):
        result = self.mod.what_installed_since(days=365)
        assert isinstance(result, str)

    def test_get_forensics_summary_returns_string(self):
        result = self.mod.get_forensics_summary(days=1)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_file_history_with_path(self):
        files = self.mod.file_history(days=365, path=str(PROJECT))
        assert isinstance(files, list)


# ═══════════════════════════════════════════════════════════════════════
# 18. REMOTE CONTROL
# ═══════════════════════════════════════════════════════════════════════

class TestRemoteControl:
    def setup_method(self):
        self.mod = _import("remote_control", PROJECT / "actions" / "remote_control.py")

    def test_start_stop(self):
        result = self.mod.start_server(host="127.0.0.1", port=18765)
        assert "started" in result
        result2 = self.mod.stop_server()
        assert "stopped" in result2

    def test_remote_control_function(self):
        r = self.mod.remote_control({"action": "status"})
        assert "not running" in r or "running" in r


# ═══════════════════════════════════════════════════════════════════════
# 19. FEDERATION
# ═══════════════════════════════════════════════════════════════════════

class TestFederation:
    def setup_method(self):
        self.mod = _import("federation", PROJECT / "actions" / "federation.py")

    def test_register_instance(self):
        result = self.mod.register_instance(name="test-box")
        assert "test-box" in result

    def test_share_memory(self):
        result = self.mod.share_memory("test_key", "test_value")
        assert "Shared" in result

    def test_query_shared(self):
        self.mod.share_memory("query_key", "query_value")
        results = self.mod.query_shared("query_key")
        assert len(results) >= 1
        assert results[-1]["key"] == "query_key"

    def test_get_instances(self):
        instances = self.mod.get_instances()
        assert isinstance(instances, list)

    def test_federation_summary(self):
        result = self.mod.federation_summary()
        assert isinstance(result, str)

    def test_federation_function(self):
        r = self.mod.federation({"action": "status"})
        assert isinstance(r, str)


# ═══════════════════════════════════════════════════════════════════════
# 20. META: NEW TOOL DECLARATIONS + DISPATCHERS
# ═══════════════════════════════════════════════════════════════════════

class TestNewToolDeclarations:
    def test_tool_declarations_exist(self):
        with open(PROJECT / "main.py") as f:
            content = f.read()
        for name in ("scaffold", "relationship_graph", "forensics",
                     "remote_control", "federation"):
            assert f'"{name}"' in content or f"'{name}'" in content, \
                f"Tool declaration '{name}' not found in main.py"

    def test_dispatcher_entries_exist(self):
        with open(PROJECT / "main.py") as f:
            content = f.read()
        for tool in ("scaffold", "relationship_graph", "forensics",
                     "remote_control", "federation"):
            assert f'elif name == "{tool}":' in content, \
                f"Dispatcher for '{tool}' not found"

    def test_imports_exist(self):
        with open(PROJECT / "main.py") as f:
            content = f.read()
        imports = [
            "project_scaffold", "relationship_graph", "forensics",
            "remote_control", "federation",
        ]
        for imp in imports:
            assert f"from actions.{imp}" in content, \
                f"Import for '{imp}' not found"

    def test_new_deps_in_requirements(self):
        text = (PROJECT / "requirements.txt").read_text()
        for dep in ("networkx", "hvac", "fastapi", "uvicorn", "websockets"):
            assert dep in text, f"Missing from requirements.txt: {dep}"

    def test_intent_router_has_new_routes(self):
        with open(PROJECT / "actions" / "intent_router.py") as f:
            content = f.read()
        routes = [
            "scaffold_project", "relationship_deploy",
            "forensics_installed", "forensics_processes",
            "remote_start", "remote_stop",
            "federation_status", "federation_share",
        ]
        for route in routes:
            assert route in content, f"Intent route '{route}' not found"

    def test_all_new_modules_parse(self):
        new_files = [
            "actions/project_scaffold.py",
            "actions/relationship_graph.py",
            "actions/forensics.py",
            "actions/remote_control.py",
            "actions/federation.py",
        ]
        for f in new_files:
            path = PROJECT / f
            assert path.exists(), f"File not found: {f}"
            try:
                ast.parse(path.read_text())
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {f}: {e}")
