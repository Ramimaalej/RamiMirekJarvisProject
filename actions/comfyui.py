import base64
import json
import logging
import random
import subprocess
import sys
import time
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image

logger = logging.getLogger("comfyui")

_COMFY_DIR = Path.home() / "ComfyUI"
_COMFY_PORT = 8188
_BASE_DIR = Path(__file__).resolve().parent.parent
_OUTPUT_DIR = _BASE_DIR / "output"


def _save_image(img: Image.Image, prefix: str = "gen") -> str:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    path = _OUTPUT_DIR / f"{prefix}_{ts}.png"
    img.save(path)
    return str(path)


# ── Local Diffusers (free, no API key) ────────────────────────────────

_MODEL_ID = "segmind/tiny-sd"


def _diffusers_generate(prompt: str, negative: str = "") -> str | None:
    try:
        from diffusers import DiffusionPipeline
        import torch
    except ImportError:
        return None
    try:
        pipe = DiffusionPipeline.from_pretrained(
            _MODEL_ID,
            torch_dtype=torch.float32,
            safety_checker=None,
        )
        if torch.cuda.is_available():
            pipe.to("cuda")
        result = pipe(
            prompt,
            negative_prompt=negative or None,
            num_inference_steps=25,
            width=512,
            height=512,
        )
        img = result.images[0]
        return _save_image(img)
    except Exception as e:
        logger.warning("Diffusers failed: %s", e)
        return None


# ── Ollama image generation ─────────────────────────────────────────────

_OLLAMA_URL = "http://localhost:11434"


def _ollama_generate(prompt: str) -> str | None:
    import httpx
    try:
        r = httpx.post(
            f"{_OLLAMA_URL}/api/generate",
            json={"model": "qwen2.5:7b", "prompt": prompt, "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        raw = data.get("response", "")
        images_b64 = data.get("images")
        if images_b64:
            for b64_str in images_b64:
                raw_bytes = base64.b64decode(b64_str)
                mime = _detect_mime(raw_bytes)
                img = Image.open(BytesIO(raw_bytes))
                return _save_image(img, "ollama")
        if raw and "generated" in raw.lower() and "image" in raw.lower():
            return f"Ollama response: {raw[:200]}"
        return None
    except Exception as e:
        logger.warning("Ollama image gen failed: %s", e)
        return None


def _detect_mime(data: bytes) -> str:
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:2] in (b"\xff\xd8",):
        return "image/jpeg"
    if data[:4] == b"RIFF":
        return "image/webp"
    return "image/png"


# ── ComfyUI ───────────────────────────────────────────────────────────


def _comfyui_running() -> bool:
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{_COMFY_PORT}/")
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _comfyui_installed() -> bool:
    return (_COMFY_DIR / "main.py").exists()


def _install_comfyui():
    if _comfyui_installed():
        return
    logger.info("Cloning ComfyUI...")
    subprocess.run(
        ["git", "clone", "https://github.com/comfyanonymous/ComfyUI.git",
         str(_COMFY_DIR)],
        capture_output=True, timeout=300,
    )
    req_path = _COMFY_DIR / "requirements.txt"
    if req_path.exists():
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req_path)],
            capture_output=True, timeout=300,
        )


def _start_comfyui():
    if _comfyui_running():
        return True
    if not _comfyui_installed():
        return False
    subprocess.Popen(
        [sys.executable, "main.py", "--listen", "127.0.0.1",
         f"--port={_COMFY_PORT}"],
        cwd=str(_COMFY_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        if _comfyui_running():
            return True
        time.sleep(1)
    return False


_COMFY_TXT2IMG_WORKFLOW = {
    "3": {
        "inputs": {"seed": 0, "steps": 25, "cfg": 7, "sampler_name": "euler",
                    "scheduler": "normal", "denoise": 1},
        "class_type": "KSampler",
    },
    "4": {
        "inputs": {"ckpt_name": ""},
        "class_type": "CheckpointLoaderSimple",
    },
    "5": {
        "inputs": {"width": 512, "height": 512, "batch_size": 1},
        "class_type": "EmptyLatentImage",
    },
    "6": {
        "inputs": {"text": "", "clip": ["11", 0]},
        "class_type": "CLIPTextEncode",
    },
    "7": {
        "inputs": {"text": "", "clip": ["11", 0]},
        "class_type": "CLIPTextEncode",
    },
    "8": {
        "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
        "class_type": "VAEDecode",
    },
    "9": {
        "inputs": {"images": ["8", 0], "filename_prefix": "jarvis"},
        "class_type": "SaveImage",
    },
    "11": {
        "inputs": {},
        "class_type": "CLIPLoader",
    },
}


def _comfyui_generate(prompt: str, negative: str = "") -> str | None:
    if not _comfyui_running():
        return None
    workflow = json.loads(json.dumps(_COMFY_TXT2IMG_WORKFLOW))
    workflow["6"]["inputs"]["text"] = prompt
    workflow["7"]["inputs"]["text"] = negative or ""
    workflow["3"]["inputs"]["seed"] = random.randint(0, 2**31)

    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{_COMFY_PORT}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    prompt_id = result.get("prompt_id", "")

    for _ in range(60):
        try:
            req2 = urllib.request.Request(
                f"http://127.0.0.1:{_COMFY_PORT}/history/{prompt_id}")
            with urllib.request.urlopen(req2, timeout=5) as r2:
                history = json.loads(r2.read())
            outputs = history.get(prompt_id, {}).get("outputs", {})
            for node_id, node_out in outputs.items():
                for img_data in node_out.get("images", []):
                    img_fn = img_data.get("filename", "")
                    if img_fn:
                        img_url = (
                            f"http://127.0.0.1:{_COMFY_PORT}/view?"
                            f"filename={img_fn}&type=output"
                        )
                        req3 = urllib.request.Request(img_url)
                        with urllib.request.urlopen(req3, timeout=10) as r3:
                            img = Image.open(BytesIO(r3.read()))
                            return _save_image(img, "comfy")
            time.sleep(1)
        except Exception:
            time.sleep(1)
    return None


# ── Public API ────────────────────────────────────────────────────────


def generate_image(parameters: dict = None, **kwargs) -> str:
    params = parameters or {}
    prompt = params.get("prompt", "").strip()
    if not prompt:
        return "Please provide an image prompt."
    negative = params.get("negative", "").strip()

    # 1. Try ComfyUI (local)
    path = _comfyui_generate(prompt, negative)
    if path:
        return f"Image generated via ComfyUI: {path}"

    # 2. Try Ollama (local, qwen2.5:7b or other model with image output)
    path = _ollama_generate(prompt)
    if path:
        return f"Image generated via Ollama: {path}"

    # 3. Try local diffusers (free, no API key)
    path = _diffusers_generate(prompt, negative)
    if path:
        return f"Image generated locally: {path}"

    # 4. Try to set up ComfyUI
    if not _comfyui_installed():
        try:
            _install_comfyui()
        except Exception:
            pass
    try:
        if _start_comfyui():
            path = _comfyui_generate(prompt, negative)
            if path:
                return f"Image generated via ComfyUI: {path}"
    except Exception:
        pass

    return (
        "I cannot do that. To generate images:\n"
        "1. Install ComfyUI: git clone https://github.com/comfyanonymous/ComfyUI\n"
        "2. Then download a model (e.g. from huggingface.co/stabilityai)"
    )
