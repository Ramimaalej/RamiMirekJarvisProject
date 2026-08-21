"""Screen text search — find a word/text on the current screen via OCR.

Intents: screen_find_text ("find 'error' on my screen", "is the word login visible
         on screen", "search the screen for password")
"""
import logging
import platform
import re

logger = logging.getLogger("screen_ocr")


def _grab() -> "Image":
    """Capture the whole screen."""
    from PIL import Image  # noqa: E402
    system = platform.system()
    if system == "Windows":
        from PIL import ImageGrab  # noqa: E402
        return ImageGrab.grab()
    try:
        import subprocess  # noqa: E402
        tmp = "/tmp/jarvis_screen.png"
        if system == "Darwin":
            subprocess.run(["screencapture", "-x", tmp], timeout=15, check=True)
        else:
            subprocess.run(["import", "-window", "root", tmp], timeout=15, check=False)
        return Image.open(tmp)
    except Exception:
        pass
    try:
        from PyQt6.QtWidgets import QApplication  # noqa: E402
        from PyQt6.QtGui import QGuiApplication  # noqa: E402
        qapp = QApplication.instance() or QApplication([])
        screen = QGuiApplication.primaryScreen()
        img = screen.grabWindow(0)
        return Image.fromqpixmap(img)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"cannot capture screen: {exc}") from exc


def _ocr_text(img: "Image") -> str:
    import pytesseract  # noqa: E402
    return pytesseract.image_to_string(img.convert("RGB"), timeout=30)


def screen_vision(parameters: dict | None = None, player=None) -> str:
    """Analyze the current screen (OCR + Visual Description)."""
    parameters = parameters or {}
    query = (parameters.get("query") or parameters.get("text") or "").strip()
    
    try:
        img = _grab()
        # Save to a temporary file for the UI or LLM to see
        tmp_path = "/tmp/jarvis_vision.png"
        img.save(tmp_path)
        if player:
            player.write_log(f"[VISION] Captured screen to {tmp_path}")
    except Exception as exc:
        logger.warning("screen capture error: %s", exc)
        return "I'm sorry, I could not capture your screen. Please check permissions."

    # Perform OCR
    try:
        text = _ocr_text(img)
        norm_text = re.sub(r"\s+", " ", text).strip()
    except Exception:
        norm_text = ""

    if not query:
        if norm_text:
            return f"I can see your screen. Here is what's written:\n\n{norm_text[:500]}..."
        return "I can see your screen, but I couldn't extract any text. It looks like a purely visual interface."

    # If searching for specific text
    if query.lower() in norm_text.lower():
        return f"Yes, I found '{query}' on your screen. (Context: {norm_text[:300]})"
    
    return f"I see your screen, but I don't see '{query}'. Here is a summary of the visible text: {norm_text[:200]}..."

def screen_find_text(parameters: dict | None = None, player=None) -> str:
    return screen_vision(parameters, player)
