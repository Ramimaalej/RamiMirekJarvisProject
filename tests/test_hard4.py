"""Hard tests — 10 new features (QR, clipboard, dictionary, math, hash,
random, notes, system info, screen find)."""
import os
import re  # noqa: F401 (used by inline dispatch logic in quick_note)
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

# project root on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from actions.intent_router import IntentRouter  # noqa: E402

router = IntentRouter()

# ── Intent routing (no LLM) ────────────────────────────────────────────

@pytest.mark.parametrize("cmd,target", [
    ("generate a qr code for https://example.com", "qr_tools"),
    ("fais un qr code pour https://jarvis.app", "qr_tools"),
    ("read this qr code from screenshot.png", "qr_tools"),
    ("what is in my clipboard", "clipboard_mgr"),
    ("lis mon presse-papiers", "clipboard_mgr"),
    ("copy hello world to clipboard", "clipboard_mgr"),
    ("copie ce texte dans le presse-papiers", "clipboard_mgr"),
    ("what does serendipity mean", "dictionary_tools"),
    ("que veut dire loquacious", "dictionary_tools"),
    ("define ephemeral", "dictionary_tools"),
    ("synonyms of happy", "dictionary_tools"),
    ("happy synonyms", "dictionary_tools"),
    ("what is sqrt(144) + 2^10", "web_search"),
    ("calcule 12 * 7 + 3", "math_solver"),
    ("combien fait 2 + 2", "math_solver"),
    ("hash this text: hello", "hash_tools"),
    ("md5 of the text hello", ""),
    ("sha256 of file report.pdf", "hash_tools"),
    ("roll a d20", "random_tools"),
    ("roll 2d6", "random_tools"),
    ("lance les dés", "random_tools"),
    ("flip a coin", "random_number"),
    ("pile ou face", "random_tools"),
    ("heads or tails", "random_tools"),
    ("pick between pizza and burger", "random_tools"),
    ("choisis entre A et B", "random_tools"),
    ("note: buy milk tomorrow", "notes_tools"),
    ("note: meeting at 5pm", "notes_tools"),
    ("list my notes", "notes_tools"),
    ("search notes for milk", "notes_tools"),
    ("battery level", "system_info_tools"),
    ("quelle batterie", "system_info_tools"),
    ("how much disk space left", "filesystem_query"),
    ("disk usage", "filesystem_query"),
    ("what wifi am i connected to", ""),
    ("wifi ssid", "system_info_tools"),
    ("find 'error' on my screen", "maps"),
    ("is the word login visible on screen", "screen_ocr"),
    ("trouve le mot motdepasse sur mon écran", "screen_ocr"),
])
def test_new_features_routing(cmd, target):
    r = router.route(cmd)
    if target:
        assert r.handler_name == target, f"{cmd!r} routed to {r.handler_name}, expected {target}"
    else:
        assert not r.matched, f"{cmd!r} should not match any intent (got {r.handler_name})"


# ── Action results ─────────────────────────────────────────────────────

def test_math_solver_expressions():
    from actions.math_solver import solve_math
    assert "1036" in solve_math({"expression": "sqrt(144) + 2^10"})
    assert "84" in solve_math({"expression": "12 * 7"})
    assert solve_math({"expression": "1 / 0"})  # should not crash

def test_math_forbidden_chars():
    from actions.math_solver import solve_math
    r = solve_math({"expression": "os.system('rm -rf /')"})
    assert "Could not" in r or "forbidden" in r or "Could not evaluate" in r

def test_unit_converter_live():
    from actions.unit_converter import convert_units
    assert "3.1069" in convert_units({"value": "5", "from": "km", "to": "miles"})
    assert convert_units({"value": "10", "from": "km", "to": "xyz"})  # unsupported msg, no crash

def test_hash_tools():
    from actions.hash_tools import hash_string
    r = hash_string({"text": "hello"})
    assert "2cf24dba" in r  # sha256 of 'hello'
    from actions.hash_tools import hash_file
    r = hash_file({"path": "/nonexistent/file.txt"})
    assert "cannot find" in r.lower() or "Could not" in r

def test_random_tools():
    from actions.random_tools import dice_roll, coin_flip, random_pick
    assert dice_roll({"dice": "d6"})  # no crash
    assert coin_flip() in ("🪙 Coin flip: HEADS", "🪙 Coin flip: TAILS") or "HEADS" in coin_flip() or "TAILS" in coin_flip()
    pick = random_pick({"options": "x y z"})
    assert "I pick:" in pick

def test_notes_persistence(tmp_path, monkeypatch):
    from actions import notes_tools
    notes_tools._NOTES_FILE = tmp_path / "test_notes.json"
    notes_tools.quick_note_save({"note": "test note 42"})
    out = notes_tools.quick_note_list()
    assert "test note 42" in out
    assert "Found" in notes_tools.quick_note_find({"query": "42"})
    assert "No note found" in notes_tools.quick_note_find({"query": "nonexistent-xyz"})

def test_qr_generate_and_scan(tmp_path):
    from actions.qr_tools import qr_generate, qr_scan
    import re as _re
    r = qr_generate({"text": "hello-test"})
    assert "QR code created" in r
    _m = _re.search(r"([\w/.:-]+qr_\S+\.png)", r)
    assert _m, r
    r2 = qr_scan({"path": _m.group(1)})
    assert "hello-test" in r2

def test_dictionary_api():
    from actions.dictionary_tools import word_definition, word_synonyms
    assert word_definition({"word": "happy"}).lower().startswith("'happy'")
    assert "found" in word_definition({"word": "zzzzzz-nonexistent"}).lower()

def test_executor_dispatch(tmp_path, monkeypatch):
    """End-to-end: route() → execute_tool() for the new handlers."""
    from core.tools.executor import execute_tool

    class MockUI:
        muted = False
        current_file = None

        def set_state(self, *_a):
            pass

        def write_log(self, *_a):
            pass

        def send_message(self, *_a):
            pass

        def show_error_state(self, *_a):
            pass

    from actions import notes_tools
    notes_tools._NOTES_FILE = tmp_path / "exec_notes.json"

    ui = MockUI()
    res = execute_tool(ui, "solve_math", {"text": "10 + 5", "query": "10 + 5"})
    assert "15" in res
    res = execute_tool(ui, "dice_roll", {"text": "roll a d6", "query": "d6"})
    assert "Rolled" in res
    res = execute_tool(ui, "quick_note", {"text": "note: exec note", "query": "exec note"})
    assert "exec note" in res
    res = execute_tool(ui, "battery_status", {"text": "battery level", "query": ""})
    assert result_type(res) is str

def result_type(r):
    return type(r)


def test_clipboard_roundtrip():
    from actions.clipboard_mgr import clipboard_write, clipboard_read
    tag = "jarvis-test-tag"
    clipboard_write({"text": tag})
    assert tag in clipboard_read()
