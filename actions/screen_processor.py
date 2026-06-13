"""
MARK XL — Screen / Camera Processor
Replaces Gemini Live vision session with a direct Ollama vision-model call.
The analysis text is returned (and optionally spoken via the `speak` callback).
"""
from __future__ import annotations

import base64
import io
import json
import sys
from pathlib import Path
from typing import Optional, Callable

try:
    import cv2
    _CV2 = True
except ImportError:
    _CV2 = False

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False

try:
    import PIL.Image
    _PIL = True
except ImportError:
    _PIL = False

import platform

import requests


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE        = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"

_IMG_MAX_W = 640
_IMG_MAX_H = 360
_JPEG_Q    = 60


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config_key(key: str, value) -> None:
    try:
        cfg = _load_config()
        cfg[key] = value
        _CONFIG_PATH.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
    except Exception as e:
        print(f"[Vision] ⚠️ Could not save config key '{key}': {e}")


def _get_os() -> str:
    s = platform.system().lower()
    if s == "darwin":  return "mac"
    if s == "windows": return "windows"
    return "linux"


# ---------------------------------------------------------------------------
# Image capture helpers (unchanged from original)
# ---------------------------------------------------------------------------

def _compress(img_bytes: bytes, source_format: str = "PNG") -> tuple[bytes, str]:
    if not _PIL:
        return img_bytes, f"image/{source_format.lower()}"
    try:
        img = PIL.Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=False)
        return buf.getvalue(), "image/jpeg"
    except Exception as e:
        print(f"[Vision] ⚠️ Image compress failed: {e}")
        return img_bytes, f"image/{source_format.lower()}"


def _capture_screen() -> tuple[bytes, str]:
    if not _MSS:
        raise RuntimeError("mss is not installed. Run: pip install mss")
    with mss.mss() as sct:
        monitors = sct.monitors
        target   = monitors[1] if len(monitors) > 1 else monitors[0]
        shot     = sct.grab(target)
        png      = mss.tools.to_png(shot.rgb, shot.size)
    return _compress(png, "PNG")


def _cv2_backend() -> int:
    if not _CV2:
        return 0
    os_name = _get_os()
    if os_name == "windows":
        return cv2.CAP_DSHOW
    if os_name == "mac":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_ANY


def _probe_camera(index: int, backend: int, warmup: int = 5) -> bool:
    if not _CV2:
        return False
    import numpy as np
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release(); return False
    for _ in range(warmup):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return False
    return bool(np.mean(frame) > 8)


def _detect_camera_index() -> int:
    backend = _cv2_backend()
    print("[Vision] 🔍 Auto-detecting camera…")
    for idx in range(6):
        if _probe_camera(idx, backend):
            print(f"[Vision] ✅ Camera found at index {idx}")
            _save_config_key("camera_index", idx)
            return idx
        print(f"[Vision] ⚠️ Camera index {idx}: no usable frame")
    print("[Vision] ⚠️ No camera found — defaulting to index 0")
    _save_config_key("camera_index", 0)
    return 0


def _get_camera_index() -> int:
    cfg = _load_config()
    if "camera_index" in cfg:
        return int(cfg["camera_index"])
    return _detect_camera_index()


def _capture_camera() -> tuple[bytes, str]:
    if not _CV2:
        raise RuntimeError("OpenCV (cv2) is not installed. Run: pip install opencv-python")
    import numpy as np
    index   = _get_camera_index()
    backend = _cv2_backend()
    cap     = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        raise RuntimeError(f"Camera index {index} could not be opened.")
    for _ in range(10):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        raise RuntimeError("Camera returned no frame.")
    if _PIL:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(rgb)
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q)
        return buf.getvalue(), "image/jpeg"
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_Q])
    return buf.tobytes(), "image/jpeg"


# ---------------------------------------------------------------------------
# Vision analysis via Ollama
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are JARVIS — a precise, efficient AI assistant. "
    "Analyze the screen or image with accuracy. "
    "Describe what you see: the main window, key UI elements (buttons, text fields, "
    "links), their labels and positions, and any notable content. "
    "If the user asks a specific question about the screen, answer it directly. "
    "Be concise — maximum 3 sentences unless the user asks for detail."
)

# ---------------------------------------------------------------------------
# UI element extraction (NeuralAgent-inspired)
# ---------------------------------------------------------------------------

try:
    import psutil as _psutil
except ImportError:
    _psutil = None

try:
    import pyatspi as _pyatspi
except ImportError:
    _pyatspi = None


def _get_running_apps() -> list[dict]:
    if not _psutil:
        return []
    system = platform.system()
    apps = []
    if system == "Linux":
        import subprocess
        try:
            output = subprocess.check_output(["wmctrl", "-lp"], stderr=subprocess.DEVNULL).decode()
            active_out = subprocess.check_output(
                ["xdotool", "getactivewindow", "getwindowpid"], stderr=subprocess.DEVNULL
            ).decode().strip()
            active_pid = int(active_out) if active_out.isdigit() else None
            seen = set()
            for line in output.splitlines():
                parts = line.split()
                if len(parts) >= 5:
                    pid = int(parts[2])
                    if pid not in seen:
                        seen.add(pid)
                        try:
                            name = _psutil.Process(pid).name()
                            apps.append({"pid": pid, "name": name, "focused": pid == active_pid})
                        except _psutil.NoSuchProcess:
                            pass
        except Exception:
            pass
    return apps


def _extract_ui_elements_linux() -> list[dict]:
    if not _pyatspi:
        return []
    try:
        desktop = _pyatspi.Registry.getDesktop(0)
    except Exception:
        return []
    elements = []
    def _recurse(obj, depth=0):
        try:
            role = obj.getRoleName()
            name = obj.name or ""
        except Exception:
            return
        interactive = {"push button", "check box", "combo box", "text", "hyperlink", "menu item",
                       "toggle button", "spin button", "slider", "list item", "table cell"}
        if role.lower() in interactive:
            try:
                box = _extract_extents(obj)
            except Exception:
                box = None
            elements.append({
                "type": role.title().replace(" ", ""),
                "label": name[:80],
                "bbox": box,
                "depth": depth,
            })
        try:
            for i in range(obj.childCount):
                _recurse(obj.getChildAtIndex(i), depth + 1)
        except Exception:
            pass
    _recurse(desktop)
    return elements


def _extract_extents(obj) -> dict | None:
    try:
        box = obj.queryComponent().getExtents(0)
        return {"x": box.x, "y": box.y, "w": box.width, "h": box.height}
    except Exception:
        return None


def _describe_ui_context() -> str:
    parts = []
    apps = _get_running_apps()
    if apps:
        focused = [a["name"] for a in apps if a.get("focused")]
        others = [a["name"] for a in apps if not a.get("focused") and a["name"] not in focused]
        if focused:
            parts.append(f"Active window: {focused[0]}")
        if others:
            parts.append(f"Open apps: {', '.join(others[:8])}")

    if platform.system() == "Linux":
        ui_el = _extract_ui_elements_linux()
        if ui_el:
            seen = set()
            lines = []
            for el in ui_el[:25]:
                key = f"{el['type']}:{el['label']}"
                if key not in seen:
                    seen.add(key)
                    loc = ""
                    if el["bbox"]:
                        loc = f" @({el['bbox']['x']},{el['bbox']['y']})"
                    lines.append(f"  [{el['type']}] \"{el['label']}\"{loc}")
            if lines:
                parts.append("UI elements visible:")
                parts.extend(lines[:15])

    return "\n".join(parts) if parts else ""

# ---------------------------------------------------------------------------
# Vision model selection helpers
# ---------------------------------------------------------------------------

_VISION_CAPABLE_MODELS: dict[str, set[str]] = {
    "nvidia_nim": {
        "meta/llama-3.2-11b-vision-instruct",
        "meta/llama-3.2-90b-vision-instruct",
        "meta/llama-4-maverick-17b-128e-instruct",
        "microsoft/phi-4-multimodal-instruct",
    },
    "openai": {
        "gpt-4o", "gpt-4o-mini", "gpt-4-vision-preview",
    },
    "openrouter": set(),
}


def _is_vision_model(provider: str, model: str) -> bool:
    candidates = _VISION_CAPABLE_MODELS.get(provider, set())
    if not candidates:
        return True
    lm = model.lower()
    return any(c in lm for c in candidates)


_VISION_FALLBACK: dict[str, str] = {
    "nvidia_nim": "meta/llama-3.2-11b-vision-instruct",
    "openai":     "gpt-4o-mini",
    "openrouter": "",
}


def _get_vision_fallback(provider: str, current_model: str) -> str:
    fallback = _VISION_FALLBACK.get(provider, "")
    if fallback and fallback.lower() != current_model.lower():
        print(f"[Vision] Model '{current_model}' not vision-capable, using '{fallback}'")
    return fallback or current_model


def _call_vision(image_bytes: bytes, mime: str, user_text: str, angle: str = "screen") -> str:
    cfg          = _load_config()
    url          = cfg.get("llm_url", "http://localhost:11434").rstrip("/")
    provider     = cfg.get("llm_provider", "ollama").strip().lower().replace(" ", "_").replace("-", "_")

    # Auto-pick a vision-capable model when the provider's default doesn't support vision
    llm_model = cfg.get("llm_model", "llava").lower()
    vision_model = cfg.get("vision_model") or ""
    if not vision_model or not _is_vision_model(provider, vision_model):
        vision_model = _get_vision_fallback(provider, llm_model)
    is_openai    = provider in ("openai", "nvidia_nim", "openrouter")

    # Enrich prompt with UI context when analysing the screen
    if angle == "screen" and not cfg.get("llm_provider", "").startswith("ollama"):
        ui_context = _describe_ui_context()
        if ui_context:
            user_text = f"{user_text}\n\nDesktop context:\n{ui_context}"

    print(f"[Vision] provider={provider} model={vision_model} url={url} size={len(image_bytes)} bytes")
    b64 = base64.b64encode(image_bytes).decode("ascii")

    if is_openai:
        endpoint = f"{url}/chat/completions" if "/v1" in url else f"{url}/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        api_key = cfg.get("llm_api_key", "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/anomalyco/opencode"
            headers["X-Title"] = "MARK XL"
        payload = {
            "model":  vision_model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                },
            ],
            "max_tokens": 300,
        }
    else:
        payload = {
            "model":  vision_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role":    "user",
                    "content": user_text,
                    "images":  [b64],
                },
            ],
        }
    try:
        endpoint = f"{url}/api/chat" if not is_openai else endpoint
        headers = headers if is_openai else {}
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if is_openai:
            return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        return (data.get("message", {}).get("content") or "").strip()
    except requests.exceptions.ConnectionError:
        return "Cannot connect to LLM server. Make sure it is running."
    except Exception as e:
        return f"Vision analysis failed: {e}"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def screen_process(
    parameters:     dict,
    response=None,
    player=None,
    session_memory=None,
    speak:          Optional[Callable[[str], None]] = None,
) -> str:
    """
    Capture screen or camera, analyse with Ollama vision model.

    Returns the analysis text (str).
    Optionally speaks via `speak` callback and logs to `player`.
    """
    params    = parameters or {}
    user_text = (params.get("text") or params.get("user_text") or "").strip()
    angle     = params.get("angle", "screen").lower().strip()

    if not user_text:
        user_text = "What do you see? Describe briefly."

    if player:
        player.write_log(f"SYS: Vision [{angle}] — {user_text[:60]}")

    # Capture
    try:
        if angle == "camera":
            image_bytes, mime = _capture_camera()
            print(f"[Vision] 📷 Camera: {len(image_bytes):,} bytes")
        else:
            image_bytes, mime = _capture_screen()
            print(f"[Vision] 🖥️  Screen: {len(image_bytes):,} bytes")
    except Exception as e:
        msg = f"Capture error: {e}"
        print(f"[Vision] ❌ {msg}")
        if player: player.write_log(f"ERR: {msg}")
        return msg

    # Analyse
    analysis = _call_vision(image_bytes, mime, user_text, angle)
    print(f"[Vision] 💬 {analysis[:120]}")

    if player:
        player.write_log(f"Jarvis: {analysis}")

    if speak and analysis:
        speak(analysis)

    return analysis
