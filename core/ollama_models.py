"""Ollama Model Manager — list, install (pull) and delete Ollama models.

Simple manager used by the "Ollama Models" page in the UI so the user can
browse the model library, install a model with one click (with progress
reported via a callback), and delete local models — without opening a
terminal.

Pure logic, no UI dependency.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable

import requests

logger = logging.getLogger("ollama_models")

DEFAULT_URL = "http://localhost:11434"


def _base_url(cfg: dict | None = None) -> str:
    url = DEFAULT_URL
    if cfg:
        url = (cfg.get("llm_url") or url).strip() or DEFAULT_URL
    return url.rstrip("/")


def _config() -> dict:
    try:
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).parent
        else:
            base = Path(__file__).resolve().parent.parent
        return json.loads((base / "config" / "api_keys.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Library — curated list of popular Ollama models the user can install
# ---------------------------------------------------------------------------
OLLAMA_LIBRARY: list[dict[str, Any]] = [
    {"id": "qwen3:8b",        "name": "Qwen 3  8B",        "desc": "Best all-rounder — smart & fast (recommended)"},
    {"id": "qwen3:4b",        "name": "Qwen 3  4B",        "desc": "Lighter all-rounder — good for 8 GB RAM"},
    {"id": "qwen2.5:7b",      "name": "Qwen 2.5  7B",      "desc": "Proven, reliable general model"},
    {"id": "llama3.2:3b",     "name": "Llama 3.2  3B",     "desc": "Very fast, runs on most PCs"},
    {"id": "llama3.1:8b",     "name": "Llama 3.1  8B",     "desc": "Solid general model from Meta"},
    {"id": "deepseek-r1:8b",  "name": "DeepSeek R1  8B",   "desc": "Reasoning model — thinks step by step"},
    {"id": "mistral:7b",      "name": "Mistral  7B",       "desc": "Great at following instructions"},
    {"id": "gemma3:4b",       "name": "Gemma 3  4B",       "desc": "Google's open model — compact"},
    {"id": "phi4:14b",        "name": "Phi-4  14B",        "desc": "Microsoft — very smart, needs ~10 GB RAM"},
    {"id": "granite3.2:8b",   "name": "Granite 3.2  8B",   "desc": "IBM — business-oriented"},
    {"id": "qwen3:1.7b",      "name": "Qwen 3  1.7B",      "desc": "Tiny & ultra-fast — great on weak PCs"},
    {"id": "smollm2:1.7b",    "name": "SmolLM 2  1.7B",    "desc": "Tiny fast model by Hugging Face"},
]

ANY_MODEL_NOTE = "Or type any model name, e.g.  llama3.3:70b"


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def is_running(url: str | None = None) -> bool:
    """True if the Ollama server responds."""
    base = url or _config().get("llm_url") or DEFAULT_URL
    try:
        resp = requests.get(f"{base.rstrip('/')}/api/tags", timeout=3)
        return resp.status_code < 400
    except Exception:
        return False


def list_local_models(cfg: dict | None = None) -> list[dict[str, Any]]:
    """Return installed local models: [{"id": ..., "size_gb": ..., "modified": ...}]."""
    base = _base_url(cfg or _config())
    try:
        resp = requests.get(f"{base}/api/tags", timeout=5)
        resp.raise_for_status()
        out = []
        for item in resp.json().get("models", []) or []:
            details = item.get("details", {})
            size = (item.get("size") or 0) / (1024 ** 3)
            name = (item.get("name") or "").strip()
            out.append({
                "id":        name,
                "size_gb":   round(size, 2),
                "modified":  (item.get("modified_at") or "").split("T")[0],
                "family":    details.get("family", ""),
            })
        return out
    except Exception as e:
        logger.debug("list_local_models failed: %s", e)
        return []


def current_model(cfg: dict | None = None) -> str:
    cfg = cfg or _config()
    return (cfg.get("llm_model") or "").strip()


# ---------------------------------------------------------------------------
# Install (pull) & delete
# ---------------------------------------------------------------------------
def pull_model(model: str,
               on_log: Callable[[str], None] | None = None,
               on_done: Callable[[bool, str], None] | None = None,
               timeout: int = 3600) -> threading.Thread:
    """Pull a model in a background thread.
    on_log(line) is called with each progress line;
    on_done(ok, message) is called when finished.
    """
    def _worker():
        model_name = model.strip()
        if not model_name:
            on_done and on_done(False, "No model name given.")
            return
        if not is_running():
            on_done and on_done(False, "Ollama is not running. Start it with: ollama serve")
            return
        if on_log:
            on_log(f"Downloading {model_name} — this may take a while…")
        try:
            proc = subprocess.Popen(
                ["ollama", "pull", model_name],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if line and on_log:
                    on_log(line)
            proc.wait()
            if proc.returncode == 0:
                on_done and on_done(True, f"{model_name} installed successfully.")
            else:
                on_done and on_done(False, f"Pull failed (exit {proc.returncode}).")
        except FileNotFoundError:
            on_done and on_done(False, "ollama not found. Install it from https://ollama.com")
        except Exception as e:
            on_done and on_done(False, f"Pull error: {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t


def delete_model(model: str) -> tuple[bool, str]:
    """Delete a locally installed model. Returns (ok, message)."""
    if not is_running():
        return False, "Ollama is not running."
    try:
        resp = requests.delete(f"{_base_url()}/api/delete", json={"name": model}, timeout=15)
        if resp.status_code in (200, 204):
            return True, f"{model} deleted."
        return False, f"Delete failed: {resp.status_code} {resp.text}"
    except Exception as e:
        return False, f"Delete error: {e}"


if __name__ == "__main__":
    print("running?", is_running())
    print("locals:", list_local_models())
    print("current:", current_model())
