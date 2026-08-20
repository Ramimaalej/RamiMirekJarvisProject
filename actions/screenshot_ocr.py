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


def screen_find_text(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    query = (parameters.get("text") or parameters.get("query") or
             parameters.get("word") or "").strip()
    if not query:
        return "Tell me what to look for on the screen, for example: 'find error on my screen'."
    try:
        img = _grab()
    except Exception as exc:  # noqa: BLE001
        logger.warning("screen capture error: %s", exc)
        return "Could not capture the screen."
    try:
        text = _ocr_text(img)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ocr error: %s", exc)
        return ("Could not read the screen (Tesseract not installed?). "
                "On Windows install it from: https://github.com/UB-Mannheim/tesseract/releases")
    norm = re.sub(r"\s+", " ", text)
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    matches = pattern.findall(norm)
    if not matches:
        return (f"'{query}' is NOT visible on the screen. "
                f"(Screen text: {norm[:300]})")
    return f"'{query}' FOUND {len(matches)} time(s) on your screen."
