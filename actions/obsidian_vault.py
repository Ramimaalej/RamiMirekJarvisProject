import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("obsidian")

VAULT_DIR = Path(os.environ.get("OBSIDIAN_VAULT", ""))
NOTES_DIR = VAULT_DIR / "JARVIS" if VAULT_DIR else Path.home() / "Obsidian" / "JARVIS"


def set_vault_path(path: str) -> str:
    global VAULT_DIR, NOTES_DIR
    VAULT_DIR = Path(path)
    NOTES_DIR = VAULT_DIR / "JARVIS"
    if not VAULT_DIR.exists():
        return f"Vault path does not exist: {path}"
    return f"Vault set to: {path}"


def _ensure_notes_dir():
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    (NOTES_DIR / ".obsidian").mkdir(parents=True, exist_ok=True)


def save_note(title: str, content: str, folder: str = "") -> dict[str, Any]:
    _ensure_notes_dir()
    target = NOTES_DIR
    if folder:
        target = target / folder
        target.mkdir(parents=True, exist_ok=True)

    safe_name = "".join(c for c in title if c.isalnum() or c in " _-").strip()
    if not safe_name:
        safe_name = f"note-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    path = target / f"{safe_name}.md"
    header = f"---\ntitle: {title}\ncreated: {datetime.now().isoformat()}\ntags: []\n---\n\n"
    path.write_text(header + content + "\n", encoding="utf-8")
    logger.info("Note saved: %s", path)
    return {"path": str(path), "title": title, "size": len(content)}


def search_notes(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    _ensure_notes_dir()
    results = []
    for f in sorted(NOTES_DIR.rglob("*.md")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            if query.lower() in text.lower():
                results.append({
                    "path": str(f),
                    "title": f.stem,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    "snippet": text[:200].replace("---\n", "").strip(),
                })
                if len(results) >= max_results:
                    break
        except Exception:
            continue
    return results


def list_notes(folder: str = "", max_results: int = 50) -> list[dict[str, Any]]:
    _ensure_notes_dir()
    target = NOTES_DIR
    if folder:
        target = target / folder

    notes = []
    for f in sorted(target.rglob("*.md")):
        try:
            notes.append({
                "path": str(f),
                "title": f.stem,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                "size": f.stat().st_size,
            })
        except Exception:
            continue
    return notes[:max_results]


def get_all_tags() -> list[str]:
    _ensure_notes_dir()
    tags = set()
    for f in NOTES_DIR.rglob("*.md"):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            import re
            tags.update(re.findall(r"#\w+", text))
        except Exception:
            continue
    return sorted(tags)


def create_knowledge_graph() -> dict[str, Any]:
    _ensure_notes_dir()
    notes = list_notes()
    links = []
    import re
    for note in notes:
        try:
            text = Path(note["path"]).read_text(encoding="utf-8")
            wiki_links = re.findall(r"\[\[([^\]]+)\]\]", text)
            for link in wiki_links:
                links.append({"source": note["title"], "target": link.strip()})
        except Exception:
            continue

    return {
        "nodes": [{"id": n["title"], "path": n["path"]} for n in notes],
        "edges": links,
        "node_count": len(notes),
        "edge_count": len(links),
    }
