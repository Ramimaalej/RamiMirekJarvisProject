"""Unicode script-based language detection."""
from __future__ import annotations
import logging
import re
from typing import Any

_SCRIPT_RANGES = {
    "ar": [(0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
    "ru": [(0x0400, 0x04FF), (0x0500, 0x052F)],
    "zh": [(0x4E00, 0x9FFF), (0x3400, 0x4DBF)],
    "ja": [(0x3040, 0x309F), (0x30A0, 0x30FF)],
    "ko": [(0xAC00, 0xD7AF)],
    "th": [(0x0E00, 0x0E7F)],
    "he": [(0x0590, 0x05FF)],
    "el": [(0x0370, 0x03FF)],
}

def _detect_script_language(text: str) -> str | None:
    """Detect language from Unicode script ranges. Returns ISO code or None for Latin script."""
    for code, ranges in _SCRIPT_RANGES.items():
        count = 0
        for lo, hi in ranges:
            for c in text:
                if lo <= ord(c) <= hi:
                    count += 1
        if count > len(text) * 0.15:
            return code
    return None

def _auto_switch_language(self, text: str) -> None:
    """Detect user language and switch TTS voice if needed."""
    detected = _detect_script_language(text)
    if detected is None:
        return
    if detected == self._current_language:
        return
    if self._tts and hasattr(self._tts, "set_language"):
        ok = self._tts.set_language(detected)
        if ok:
            self._current_language = detected
            lang_name = {
                "ar": "Arabic", "ru": "Russian", "zh": "Chinese",
                "ja": "Japanese", "ko": "Korean", "th": "Thai",
                "he": "Hebrew", "el": "Greek",
            }.get(detected, detected)
            self.ui.write_log(f"SYS: TTS auto-switched to {lang_name}")

# ------------------------------------------------------------------
