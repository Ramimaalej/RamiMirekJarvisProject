"""Provider & Model Discovery — detects which LLM providers are available
and lists their models automatically.

Used by the Provider Selection screen (ProviderOverlay) in ui.py so the user
can pick a provider (Ollama, Groq, NVIDIA NIM, OpenRouter, OpenAI…) with a
single click — models are auto-detected for local/cloud providers that
expose a /models endpoint, otherwise sensible defaults are loaded.

No UI dependency — pure logic, safe to import and unit-test.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any, Callable

import requests

logger = logging.getLogger("llm_provider_detector")

# ---------------------------------------------------------------------------
# Provider registry — one source of truth for all known providers
# ---------------------------------------------------------------------------
# Each entry:
#   id        : key stored in config/api_keys.json as "llm_provider"
#   label     : friendly name shown in the UI
#   tagline   : one-line description shown in the UI
#   url       : default API base URL
#   url_key   : config key override (None = use llm_url)
#   key_field : config key that holds the API key (None = local / no key)
#   key_env   : optional env var name to fall back to
#   protocol  : "ollama" | "openai"
#   discover  : "models" (query /models) | "local-only" (only when reachable)
PROVIDERS: list[dict[str, Any]] = [
    {
        "id":        "ollama",
        "label":     "Ollama",
        "tagline":   "Run LLMs on your own PC — fully private, offline",
        "url":       "http://localhost:11434",
        "url_key":   None,
        "key_field": None,
        "key_env":   None,
        "protocol":  "ollama",
        "discover":  "local-only",
        "category":  "local",
    },
    {
        "id":        "groq",
        "label":     "Groq",
        "tagline":   "Blazing-fast cloud inference (Llama, Mixtral, DeepSeek)",
        "url":       "https://api.groq.com/openai/v1",
        "url_key":   None,
        "key_field": "groq_api_key",
        "key_env":   None,
        "protocol":  "openai",
        "discover":  "models",
        "category":  "cloud",
    },
    {
        "id":        "gemini",
        "label":     "Google Gemini",
        "tagline":   "Google Gemini (Nano / Flash / Pro) — one key for all",
        "url":       "https://generativelanguage.googleapis.com/v1beta/openai",
        "url_key":   None,
        "key_field": "gemini_api_key",
        "key_env":   "GOOGLE_API_KEY",
        "protocol":  "openai",
        "discover":  "models",
        "category":  "cloud",
    },
    {
        "id":        "nvidia_nim",
        "label":     "NVIDIA NIM",
        "tagline":   "NVIDIA cloud models (Llama, Nemotron, Qwen…)",
        "url":       "https://integrate.api.nvidia.com/v1",
        "url_key":   None,
        "key_field": "nvidia_api_key",
        "key_env":   None,
        "protocol":  "openai",
        "discover":  "models",
        "category":  "cloud",
    },
    {
        "id":        "openrouter",
        "label":     "OpenRouter",
        "tagline":   "One key for hundreds of models (GPT, Claude, Gemini…)",
        "url":       "https://openrouter.ai/api/v1",
        "url_key":   None,
        "key_field": "openrouter_api_key",
        "key_env":   None,
        "protocol":  "openai",
        "discover":  "models",
        "category":  "cloud",
    },
    {
        "id":        "openai",
        "label":     "OpenAI / Local",
        "tagline":   "OpenAI cloud or any local server (LM Studio, Jan…)",
        "url":       "https://api.openai.com/v1",
        "url_key":   "llm_url",
        "key_field": "openai_api_key",
        "key_env":   None,
        "protocol":  "openai",
        "discover":  "models",
        "category":  "both",
    },
]

_PROVIDER_BY_ID: dict[str, dict[str, Any]] = {p["id"]: p for p in PROVIDERS}

DEFAULT_MODELS: dict[str, list[str]] = {
    "ollama":     ["qwen3:8b", "qwen3:4b", "qwen2.5:7b", "llama3.2:3b", "deepseek-r1:8b"],
    "groq":       ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "deepseek-r1-distill-llama-70b"],
    "nvidia_nim": ["meta/llama-3.1-8b-instruct", "meta/llama-3.3-70b-instruct", "mistralai/mixtral-8x7b-instruct-v0.1", "qwen/qwen3-32b"],
    "openrouter": ["openai/gpt-4.1-mini", "anthropic/claude-sonnet-4", "google/gemini-2.5-flash", "meta-llama/llama-3.3-70b-instruct"],
    "gemini":     ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-2.5-flash-nano"],
    "openai":     ["gpt-4.1-mini", "gpt-4.1", "gpt-5-mini", "llama3.2"],
}

POLL_TIMEOUT = 6.0          # seconds per provider discovery round
_LIST_TIMEOUT = 10.0        # seconds to fetch /models or /api/tags


def get_provider(pid: str) -> dict[str, Any] | None:
    return _PROVIDER_BY_ID.get(pid)


# ---------------------------------------------------------------------------
# Reachability & model listing
# ---------------------------------------------------------------------------
def is_ollama_reachable(url: str = "http://localhost:11434", timeout: float = 3.0) -> bool:
    """Ollama-specific ping via /api/tags."""
    try:
        resp = requests.get(f"{url.rstrip('/')}/api/tags", timeout=timeout)
        return resp.status_code < 400
    except Exception:
        return False


def _is_up(url: str, headers: dict, timeout: float) -> bool:
    try:
        resp = requests.get(f"{url.rstrip('/')}/models", headers=headers, timeout=timeout)
        return resp.status_code < 400
    except Exception:
        return False


def is_reachable(pid: str, cfg: dict | None = None) -> bool:
    """True if the provider's API can be reached right now (key not required)."""
    p = _PROVIDER_BY_ID.get(pid)
    if p is None:
        return False
    cfg = cfg or _current_config()
    url = _resolve_url(p, cfg)
    headers = _headers_for(p, cfg)
    if p["protocol"] == "ollama":
        return is_ollama_reachable(url)
    return _is_up(url, headers, POLL_TIMEOUT)


def list_models(pid: str, cfg: dict | None = None, timeout: float = _LIST_TIMEOUT) -> list[str]:
    """List available models for a provider. Returns DEFAULT_MODELS on failure."""
    p = _PROVIDER_BY_ID.get(pid)
    if p is None:
        return DEFAULT_MODELS.get(pid, [])
    cfg = cfg or _current_config()
    url = _resolve_url(p, cfg)
    headers = _headers_for(p, cfg)
    try:
        if p["protocol"] == "ollama":
            resp = requests.get(f"{url.rstrip('/')}/api/tags", headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            names = []
            for item in data.get("models", []) or []:
                name = item.get("name") or item.get("model") or ""
                if name:
                    names.append(name)
            if names:
                return sorted(set(names))
        else:
            resp = requests.get(f"{url.rstrip('/')}/models", headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            names = []
            for item in data.get("data", []) or []:
                mid = item.get("id", "").strip()
                if mid and item.get("object") != "model_type" or True:
                    names.append(mid)
            if names:
                return sorted(set(n for n in names if n))
    except Exception as e:
        logger.debug("Model discovery failed for %s: %s", pid, e)
    # Provider unreachable or no key — fall back to curated defaults
    return DEFAULT_MODELS.get(pid, [])


def discover_all(cfg: dict | None = None, on_status: Callable[[str, dict], None] | None = None
                 ) -> dict[str, dict]:
    """Discover every provider concurrently.
    Returns {provider_id: {"reachable": bool, "models": [...], "default": str}}.
    Calls on_status(pid, status_dict) as each provider finishes.
    """
    cfg = cfg or _current_config()
    results: dict[str, dict] = {}
    lock = threading.Lock()

    def _probe(pid: str) -> None:
        p = _PROVIDER_BY_ID[pid]
        status: dict[str, Any] = {
            "reachable": False,
            "models": [],
            "default": "",
            "needs_key": bool(p.get("key_field")),
            "has_key": False,
        }
        key_field = p.get("key_field")
        if key_field:
            status["has_key"] = bool((cfg.get(key_field) or "").strip())
        reachable = is_reachable(pid, cfg)
        status["reachable"] = reachable
        models = list_models(pid, cfg) if reachable else []
        status["models"] = models
        status["default"] = _pick_default(pid, models, cfg)
        with lock:
            results[pid] = status
        if on_status:
            on_status(pid, status)

    threads = [threading.Thread(target=_probe, args=(p["id"],), daemon=True)
               for p in PROVIDERS]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=POLL_TIMEOUT + _LIST_TIMEOUT + 2)
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_url(p: dict, cfg: dict) -> str:
    raw = ""
    if p.get("url_key"):
        raw = (cfg.get(p["url_key"]) or "").strip()
    return raw or p["url"]


def _headers_for(p: dict, cfg: dict) -> dict:
    headers: dict[str, str] = {}
    key_field = p.get("key_field")
    if key_field:
        key = (cfg.get(key_field) or "").strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
    if p["id"] == "openrouter":
        headers.setdefault("HTTP-Referer", "https://github.com/ramimaalej/RamiMirekJarvisProject")
        headers.setdefault("X-Title", "MARK XL")
    return headers


def _pick_default(pid: str, models: list[str], cfg: dict) -> str:
    """Pick the default model: prefer the currently configured one, else first
    curated default that exists, else first listed model."""
    current = (cfg.get("llm_model") or "").strip()
    cur_provider = (cfg.get("llm_provider") or "").strip().lower().replace("-", "_")
    if cur_provider == pid and current and (not models or current in models):
        return current
    for candidate in DEFAULT_MODELS.get(pid, []):
        if not models or candidate in models:
            return candidate
    if models:
        return models[0]
    return DEFAULT_MODELS.get(pid, [""])[0]


def _current_config() -> dict:
    try:
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).parent
        else:
            base = Path(__file__).resolve().parent.parent
        return json.loads((base / "config" / "api_keys.json").read_text(encoding="utf-8"))
    except Exception:
        return {}



