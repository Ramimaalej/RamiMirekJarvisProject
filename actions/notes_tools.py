"""Quick notes — persistent plain-text notes.

Intents: quick_note_save ("note: buy milk", "save a note that meeting at 5pm"),
         quick_note_list ("list my notes", "show all notes"),
         quick_note_find ("find my note about milk", "search notes for project")
"""
import logging
import time
from pathlib import Path

logger = logging.getLogger("notes")

_NOTES_FILE: Path | None = None

MAX_NOTES = 500


def _notes_file() -> Path:
    global _NOTES_FILE
    if _NOTES_FILE is None:
        _NOTES_FILE = Path(__file__).resolve().parent.parent / "config" / "quick_notes.json"
    return _NOTES_FILE


def _load() -> list:
    import json
    try:
        return json.loads(_notes_file().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def _save(notes: list) -> None:
    import json
    _notes_file().parent.mkdir(parents=True, exist_ok=True)
    _notes_file().write_text(json.dumps(notes, indent=2, ensure_ascii=False),
                             encoding="utf-8")


def quick_note_save(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    text = (parameters.get("text") or parameters.get("note") or "").strip()
    if not text:
        return "Tell me the note to save, for example: 'note: buy milk tomorrow'."
    notes = _load()
    notes.insert(0, {"text": text, "at": time.strftime("%Y-%m-%d %H:%M")})
    if len(notes) > MAX_NOTES:
        notes = notes[:MAX_NOTES]
    _save(notes)
    return f"Note saved ({len(notes)} total): {text[:200]}"


def quick_note_list(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    count = int(parameters.get("count") or 10)
    notes = _load()
    if not notes:
        return "You have no notes yet."
    lines = [f"- [{n['at']}] {n['text'][:90]}" for n in notes[:min(count, len(notes))]]
    return f"Your notes ({len(notes)} total):\n" + "\n".join(lines)


def quick_note_find(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    query = (parameters.get("query") or parameters.get("text") or "").strip().lower()
    if not query:
        return "Tell me what to search for, for example: 'find my note about milk'."
    notes = _load()
    hits = [n for n in notes if query in n["text"].lower()]
    if not hits:
        return f"No note found containing '{query}'."
    lines = [f"- [{n['at']}] {n['text'][:90]}" for n in hits[:10]]
    return f"Found {len(hits)} note(s):\n" + "\n".join(lines)
