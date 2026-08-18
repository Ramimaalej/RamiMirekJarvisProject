"""Screen Vision — lets Jarvis see what is on your screen and read text from it.

- capture_screen() : takes a screenshot and saves it under memory/screens/.
- read_screen_text() : OCR (tesseract) on the screenshot, returns plain text.
- see_screen() : convenience wrapper — screenshot + OCR + summary for the LLM.

Pure logic, no UI dependency. Lazy imports so heavy libs (PIL, pytesseract)
never slow down startup.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def _imports():
    from PIL import ImageGrab, Image
    import pytesseract
    return ImageGrab, Image, pytesseract


SCREEN_DIR = Path(__file__).resolve().parent.parent / "memory" / "screens"


def _ensure_dir() -> Path:
    SCREEN_DIR.mkdir(parents=True, exist_ok=True)
    return SCREEN_DIR


def _cleanup_old(keep: int = 20) -> None:
    """Keep only the most recent screenshots (rolling window)."""
    try:
        files = sorted(_ensure_dir().glob("screen_*.png"), key=lambda p: p.stat().st_mtime)
        for old in files[: max(0, len(files) - keep)]:
            old.unlink()
    except Exception:
        pass


def capture_screen() -> str:
    """Take a full screenshot. Returns the file path (str)."""
    ImageGrab, Image, _ = _imports()
    d = _ensure_dir()
    path = d / f"screen_{int(time.time())}.png"
    img = ImageGrab.grab()  # full primary display
    img.save(str(path))
    _cleanup_old()
    return str(path)


def read_screen_text(path: str | None = None, lang: str = "eng") -> str:
    """OCR the given screenshot (or a fresh one if None). Returns text."""
    _, Image, pytesseract = _imports()
    if path is None:
        path = capture_screen()
    img = Image.open(path)
    text = pytesseract.image_to_string(img, lang=lang).strip()
    return text


def see_screen(lang: str = "eng") -> dict:
    """One-shot: screenshot + OCR. Returns {"path", "text", "chars"}."""
    path = capture_screen()
    text = read_screen_text(path, lang)
    return {
        "path":  path,
        "text":  text,
        "chars": len(text),
    }


def format_screen_summary(data: dict, max_chars: int = 2500) -> str:
    """Format OCR output for the LLM context."""
    text = data.get("text", "")
    if not text:
        return "The screen is empty or contains only images (no readable text)."
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n…(truncated, {len(text)} chars total)"
    return f"SCREEN TEXT ({len(text)} chars):\n{text}"
