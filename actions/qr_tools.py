"""QR code tools — generate a QR code from text/URL and decode one from an image.

Intents: qr_generate ("generate a qr code for https://example.com",
         "fais un qr code pour ..."), qr_scan ("read this qr code from file ...")
"""
import logging
from pathlib import Path

logger = logging.getLogger("qr_tools")

_QR_DIR = None

def _qr_dir() -> Path:
    global _QR_DIR
    if _QR_DIR is None:
        base = Path(__file__).resolve().parent.parent
        _QR_DIR = base / "media" / "qr"
        _QR_DIR.mkdir(parents=True, exist_ok=True)
    return _QR_DIR


def qr_generate(parameters: dict | None = None, player=None) -> str:
    """Generate a QR code PNG from text or URL. Saved in media/qr/."""
    parameters = parameters or {}
    text = parameters.get("text") or parameters.get("url") or ""
    text = text.strip()
    if not text:
        return "Tell me what to encode, for example: 'generate a qr code for https://example.com'."
    try:
        import qrcode  # noqa: E402 — optional dependency
        qr = qrcode.QRCode(
            version=None, error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10, border=2)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        slug = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)[:40]
        out = _qr_dir() / f"qr_{slug}.png"
        img.save(out)
        return f"QR code created: {out} (content: {text[:200]})"
    except ImportError:
        return ("QR code generation requires the 'qrcode' package. "
                "Run: pip install qrcode  then ask me again.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("qr_generate error: %s", exc)
        return f"Could not generate the QR code: {exc}"


def qr_scan(parameters: dict | None = None, player=None) -> str:
    """Decode a QR code from an image file path."""
    parameters = parameters or {}
    path = parameters.get("path") or parameters.get("file") or parameters.get("image") or ""
    if not path:
        return "Give me an image file that contains a QR code."
    p = Path(path).expanduser()
    if not p.exists():
        return f"I cannot find {p}."
    try:
        from PIL import Image  # noqa: E402
        try:
            from pyzbar.pyzbar import decode  # noqa: E402
            found = [d.data.decode("utf-8", "replace") for d in decode(Image.open(p))]
            if found:
                return f"QR code content: {found[0]}" + (f" (and {len(found)-1} more)" if len(found) > 1 else "")
        except ImportError:
            pass  # fall through to OpenCV fallback
        try:
            import cv2  # noqa: E402
            det = cv2.QRCodeDetector()
            data, _pts, _ok = det.detectAndDecode(cv2.imread(str(p)))
            if data:
                return f"QR code content: {data}"
        except ImportError:
            pass
        return ("No QR decoder available. Install: pip install qrcode[qr] opencv-python-headless "
                "or pyzbar, then ask me again.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("qr_scan error: %s", exc)
        return f"Could not read the QR code: {exc}"
