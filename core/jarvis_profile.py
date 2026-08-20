"""Jarvis user profile — everything Jarvis knows about its user.

Reads config/user_profile.json and exposes helpers used by the LLM
system prompt and by intents like "what do you know about me".
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger("jarvis_profile")

_DEFAULT_PROFILE = {
    "name": "Rami Maalej",
    "location": "Sfax, Tunisia",
    "email": "rami.maalej.2002@gmail.com",
    "phone": "+216 54 903 705",
    "languages": ["Arabic (native)", "French (B2)", "English (B2)"],
    "education": {"degree": "B.Sc. in Computer Science", "school": "ISIMS Sfax", "year": "2026"},
    "projects": {"Jarvis": "Desktop AI assistant — Python, PyQt6, Ollama/Groq/Gemini, Whisper STT, TTS, screen OCR, browser automation"},
    "timezone": "Africa/Tunis",
    "_auto_populated": True,
}

_cache: dict | None = None


def _profile_path() -> Path:
    base = Path(__file__).resolve().parent.parent
    return base / "config" / "user_profile.json"


def load_profile() -> dict:
    """Load the user profile, creating a default one if missing."""
    global _cache
    if _cache is not None:
        return _cache
    path = _profile_path()
    if not path.exists():
        logger.info("user_profile.json missing — creating default")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_DEFAULT_PROFILE, indent=2, ensure_ascii=False), encoding="utf-8")
        _cache = dict(_DEFAULT_PROFILE)
        return _cache
    try:
        _cache = json.loads(path.read_text(encoding="utf-8"))
        return _cache
    except Exception as exc:  # noqa: BLE001
        logger.warning("profile parse error: %s", exc)
        _cache = dict(_DEFAULT_PROFILE)
        return _cache


def update_profile(patch: dict) -> dict:
    """Merge new keys into the profile and persist."""
    profile = load_profile()
    profile.update(patch)
    try:
        _profile_path().write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("profile write error: %s", exc)
    _cache = profile
    return profile


def about_summary(max_chars: int = 1200) -> str:
    """Short human-readable summary of what Jarvis knows about the user."""
    p = load_profile()

    def txt(v):
        return " ".join(str(v).split()) if isinstance(v, (list, dict)) else str(v)

    lines = [f"You are Rami Maalej, a full-stack developer from {p.get('location', 'Sfax, Tunisia')}, "
             f"{p.get('education', {}).get('degree', 'Computer Science')} graduate ({p.get('education', {}).get('school', 'ISIMS Sfax')}, {p.get('education', {}).get('year', '2026')})."]
    work = p.get("work")
    if work:
        lines.append("Experience: " + "; ".join(str(w)[:200] for w in work[:2]))
    sk = p.get("skills")
    if sk:
        lines.append("Skills: " + ", ".join(str(s) for s in sk[:12]))
    projects = p.get("projects")
    if projects and isinstance(projects, dict):
        lines.append("Projects: " + ", ".join(k for k in projects))
    lines.append(f"Languages: {', '.join(str(l) for l in p.get('languages', []))}. "
                 f"Contact: {p.get('email', '')} / {p.get('phone', '')}.")
    out = " ".join(lines)
    return out[:max_chars]


def profile_for_prompt(max_chars: int = 1600) -> str:
    """Markdown snippet injected into the system prompt so the LLM
    always knows everything about the user without asking."""
    p = load_profile()
    chunk = json.dumps(p, indent=2, ensure_ascii=False)
    return ("USER PROFILE — everything Jarvis knows about its user (do not ask for facts already here):\n"
            + chunk)[:max_chars]
