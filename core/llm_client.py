"""
Local LLM client for MARK XL.

Supports multiple backends — selected via  "llm_provider"  in config/api_keys.json:

  "llm_provider": "ollama"   (default)
        Uses Ollama's native /api/chat endpoint.
        Download: https://ollama.com
        Default port: 11434

  "llm_provider": "openai"
        Uses any OpenAI-compatible server: LM Studio, Jan, LocalAI,
        llama.cpp server, vLLM, etc.
        LM Studio download: https://lmstudio.ai   (default port: 1234)
        Set  "llm_url": "http://localhost:1234"  in config.
        Note: tool-calling support depends on the model; use a model that
        supports function/tool calls (e.g. Qwen2.5, Llama-3.1, Mistral).

  "llm_provider": "nvidia_nim"
        Uses NVIDIA NIM (cloud inference API).
        Requires  "llm_api_key"  in config (NVIDIA API key).
        Default URL: https://integrate.api.nvidia.com/v1
        Models: meta/llama-3.1-8b-instruct, mistralai/mistral-7b-instruct-v0.3, etc.

  "llm_provider": "openrouter"
        Uses OpenRouter (unified API for many providers).
        Requires  "llm_api_key"  in config (OpenRouter API key).
        Default URL: https://openrouter.ai/api/v1
        Models: openai/gpt-4o, anthropic/claude-3.5-sonnet, google/gemini-2.0-flash, etc.
"""
import json
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Generator

import requests

# Matches a sentence boundary: [.!?] followed by whitespace, or a blank line.
# Avoids splitting on decimals (3.5) because those have no space after the dot.
_SENT_END = re.compile(r'(?<=[.!?])\s+|(?<=\n)\s*\n')

# ---------------------------------------------------------------------------
# Config cache — avoids repeated disk reads within the same turn
# ---------------------------------------------------------------------------
# _load_config() is called by get_llm_provider(), get_llm_settings(), and
# get_llm_headers() on every LLM call — potentially 6+ times per turn.
# A 5-second TTL collapses these into a single JSON parse per turn.
_CONFIG_CACHE:     dict  = {}
_CONFIG_CACHE_AT:  float = 0.0
_CONFIG_TTL:       float = 30.0  # seconds — reduced disk reads per turn

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR    = get_base_dir()
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

_DEFAULTS = {
    "llm_url":          "http://localhost:11434",
    "llm_url_local":    "http://localhost:11434",
    "llm_url_remote":   "",
    "llm_model":        "qwen2.5:0.5b",
    "llm_provider":     "ollama",
}

_PROVIDER_DEFAULTS: dict[str, tuple[str, str]] = {
    "ollama":      ("http://localhost:11434",                  "qwen2.5:0.5b"),
    "openai":      ("http://localhost:1234",                   "llama3.2"),
    "nvidia-nim":  ("https://integrate.api.nvidia.com/v1",    "meta/llama-3.1-8b-instruct"),
    "openrouter":  ("https://openrouter.ai/api/v1",           "openai/gpt-4o-mini"),
    "groq":        ("https://api.groq.com/openai/v1",         "llama-3.3-70b-versatile"),
}

def _is_openai_compatible(provider: str) -> bool:
    """Returns True for any provider that speaks the OpenAI chat completions protocol."""
    return provider in ("openai", "nvidia-nim", "openrouter", "groq")


def detect_network_mode() -> str:
    """Return 'local' if on a private LAN (10.x, 172.16-31.x, 192.168.x), else 'remote'."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        parts = ip.split(".")
        if parts[0] == "10":
            return "local"
        if parts[0] == "172" and 16 <= int(parts[1]) <= 31:
            return "local"
        if parts[0] == "192" and parts[1] == "168":
            return "local"
        return "remote"
    except Exception:
        return "remote"


def resolve_llm_url(cfg: dict) -> str:
    """Pick the right LLM URL based on current network, falling back to llm_url."""
    local_url  = (cfg.get("llm_url_local") or "").strip()
    remote_url = (cfg.get("llm_url_remote") or "").strip()
    if not local_url and not remote_url:
        return (cfg.get("llm_url") or _DEFAULTS["llm_url"]).rstrip("/")
    mode = detect_network_mode()
    if mode == "local" and local_url:
        return local_url.rstrip("/")
    if remote_url:
        return remote_url.rstrip("/")
    return local_url.rstrip("/") if local_url else (cfg.get("llm_url") or _DEFAULTS["llm_url"]).rstrip("/")


def get_llm_provider() -> str:
    """Returns 'ollama', 'openai', 'nvidia-nim', 'openrouter', or 'groq'."""
    raw = _load_config().get("llm_provider", "ollama").strip().lower().replace(" ", "_").replace("-", "_")
    if raw in ("nvidia_nim", "nvidia"):
        return "nvidia-nim"
    if raw in ("openrouter", "open_router"):
        return "openrouter"
    if raw in ("openai", "lmstudio", "localai", "jan", "llamacpp"):
        return "openai"
    if raw in ("groq",):
        return "groq"
    return "ollama"


def _load_config() -> dict:
    global _CONFIG_CACHE, _CONFIG_CACHE_AT
    now = time.monotonic()
    if now - _CONFIG_CACHE_AT < _CONFIG_TTL:
        return _CONFIG_CACHE
    try:
        _CONFIG_CACHE    = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        _CONFIG_CACHE_AT = now
    except Exception:
        pass  # return stale cache on error
    # Auto-resolve LLM URL from network-aware keys — only for local providers
    provider = _CONFIG_CACHE.get("llm_provider", "ollama")
    if provider not in ("groq", "openai", "openrouter", "nvidia-nim"):
        if _CONFIG_CACHE.get("llm_url_local") or _CONFIG_CACHE.get("llm_url_remote"):
            _CONFIG_CACHE["llm_url"] = resolve_llm_url(_CONFIG_CACHE)
    return _CONFIG_CACHE


def invalidate_config_cache() -> None:
    """Call this immediately after writing a new config file so the next
    LLM call picks up the changes without waiting for TTL expiry."""
    global _CONFIG_CACHE_AT
    _CONFIG_CACHE_AT = 0.0


def get_openai_endpoints(url: str) -> tuple[str, str]:
    """Returns (chat_completions_endpoint, models_endpoint) for OpenAI-compatible providers."""
    if "/v1" in url:
        return f"{url}/chat/completions", f"{url}/models"
    else:
        return f"{url}/v1/chat/completions", f"{url}/v1/models"


def get_llm_headers() -> dict:
    """Generates requests headers containing the API key if configured."""
    cfg = _load_config()
    headers = {}
    key = cfg.get("llm_api_key", "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    provider = get_llm_provider()
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/anomalyco/opencode"
        headers["X-Title"] = "MARK XL"
    return headers


def _list_ollama_models(url: str) -> list[str]:
    try:
        resp = requests.get(f"{url}/api/tags", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        models = data.get("models", []) or []
        names = []
        for item in models:
            name = item.get("name") or item.get("model") or ""
            if name:
                names.append(name.split(":", 1)[0] + (":" + name.split(":", 1)[1] if ":" in name else ""))
        return names
    except Exception:
        return []


def ensure_ollama_model(model: str) -> str:
    """Ensure the configured Ollama model exists; pull it automatically if needed."""
    url, _ = get_llm_settings()
    provider = get_llm_provider()
    if provider != "ollama":
        return model

    available = _list_ollama_models(url)
    normalized = model.strip().lower()
    if any(m.strip().lower() == normalized for m in available):
        return model

    # If the configured model is missing, try to pull it automatically.
    print(f"[LLM] Model '{model}' not found in Ollama. Pulling it now…")
    try:
        result = subprocess.run(["ollama", "pull", model], capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(stderr or "ollama pull failed")
        print(f"[LLM] Model '{model}' pulled successfully.")
        return model
    except Exception as e:
        raise RuntimeError(
            f"Ollama model '{model}' is not available. Run 'ollama pull {model}' manually. ({e})"
        )


def ensure_ollama_running(timeout: int = 15) -> bool:
    """
    For Ollama: ping /api/tags; auto-launch 'ollama serve' if not running.
    For OpenAI-compatible providers: just ping /v1/models (server must be started manually).
    Returns True if the LLM server is reachable.
    """
    url, _   = get_llm_settings()
    provider = get_llm_provider()

    if _is_openai_compatible(provider):
        _, health = get_openai_endpoints(url)
        headers = get_llm_headers()
        try:
            resp = requests.get(health, headers=headers, timeout=10)
            ok = resp.status_code in (200, 401, 403, 405)
            if ok:
                print(f"[LLM] {provider} server reachable at {url}")
            else:
                print(f"[LLM] {provider} at {url} returned {resp.status_code}.")
            return ok
        except Exception as e:
            print(f"[LLM] Cannot reach {provider} at {url}: {e}")
            return False

    # ── Ollama ──────────────────────────────────────────────────────────────
    health = f"{url}/api/tags"

    def _is_up() -> bool:
        try:
            return requests.get(health, timeout=3).status_code == 200
        except Exception:
            return False

    if _is_up():
        return True

    print("[LLM] Ollama not running — launching 'ollama serve'…")
    try:
        kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(["ollama", "serve"], **kwargs)
    except FileNotFoundError:
        print("[LLM] 'ollama' command not found. Install Ollama from https://ollama.com")
        return False
    except Exception as e:
        print(f"[LLM] Could not launch Ollama: {e}")
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1.0)
        if _is_up():
            print("[LLM] Ollama started successfully.")
            return True

    print("[LLM] Ollama did not respond within the timeout.")
    return False


def warmup_model(system_prompt: str | None = None) -> bool:
    """
    Pre-load the model AND prime Ollama's KV prefix cache.

    Cloud providers (nvidia-nim, openrouter, openai) are always-on in the cloud
    — there is nothing to "warm up" on our side.  Making an API round-trip just
    to confirm they are reachable adds 3-30 s of blocking startup time for no
    benefit.  We skip the warmup call entirely for those providers.

    For Ollama: the warmup sends the full static system prompt so Ollama
    evaluates and caches its KV state once.  Every real request then only needs
    to evaluate the small dynamic tail, dropping first-token latency from ~17 s
    to <1 s.
    """
    url, model = get_llm_settings()
    provider   = get_llm_provider()
    model = ensure_ollama_model(model) if provider == "ollama" else model

    # ── Cloud providers: skip warmup ──────────────────────────────────────────
    # nvidia-nim, openrouter and openai host models in the cloud.  Their models
    # are always loaded; a "warmup" API call would only waste time and quota.
    if _is_openai_compatible(provider):
        print(f"[LLM] '{model}' ({provider}) — cloud provider, skipping warmup.")
        return True

    # ── Ollama only from here ─────────────────────────────────────────────────
    print(f"[LLM] Warming up '{model}' (ollama) — priming KV cache…")
    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": "hi"})

    payload = {
        "model":      model,
        "messages":   messages,
        "stream":     False,
        "keep_alive": -1,
        # num_gpu:99 → push ALL transformer layers to GPU (Ollama caps at available)
        # This is safe even without a GPU — Ollama silently ignores if n_gpu_layers=0
        "options":    {"num_predict": 1, "num_gpu": 99, "num_thread": 4},
    }
    try:
        resp = requests.post(f"{url}/api/chat", json=payload, timeout=180)
        resp.raise_for_status()
        print(f"[LLM] '{model}' loaded and KV cache primed.")
        return True
    except Exception as e:
        print(f"[LLM] Warmup failed (non-fatal): {e}")
        return False



def get_llm_settings() -> tuple[str, str]:
    """Returns (base_url, model_name).

    Falls back to provider-specific defaults when the config value is empty.
    """
    cfg      = _load_config()
    provider = get_llm_provider()
    def_url, def_model = _PROVIDER_DEFAULTS.get(provider, (_DEFAULTS["llm_url"], _DEFAULTS["llm_model"]))
    url   = (cfg.get("llm_url")   or def_url).rstrip("/")
    model = cfg.get("llm_model")  or def_model
    return url, model


def call_llm(
    messages: list,
    tools:    list | None = None,
    timeout:  int = 120,
) -> dict:
    """
    Non-streaming chat request.  Routes to Ollama or OpenAI-compatible backend.

    Returns:
        {"content": str, "tool_calls": list}
    """
    url, model = get_llm_settings()
    provider   = get_llm_provider()
    model = ensure_ollama_model(model) if provider == "ollama" else model

    if _is_openai_compatible(provider):
        endpoint, _ = get_openai_endpoints(url)
        headers = get_llm_headers()
        payload: dict = {
            "model":      model,
            "messages":   messages,
            "stream":     False,
            "max_tokens": 2048,
        }
        if tools:
            payload["tools"]       = tools
            payload["tool_choice"] = "auto"
        try:
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            choice = resp.json().get("choices", [{}])[0]
            msg    = choice.get("message", {})
            # OpenAI tool_calls format → normalise to Ollama-style
            raw_tc  = msg.get("tool_calls") or []
            tc_list = [
                {
                    "id":       t.get("id", ""),
                    "type":     "function",
                    "function": {
                        "name":      t["function"]["name"],
                        "arguments": (
                            json.dumps(t["function"]["arguments"])
                            if not isinstance(t["function"].get("arguments"), str)
                            else t["function"].get("arguments", "{}")
                        ),
                    },
                }
                for t in raw_tc
            ]
            return {
                "content":    (msg.get("content") or "").strip(),
                "tool_calls": tc_list,
            }
        except Exception as e:
            raise RuntimeError(f"{provider} LLM call failed: {e}")

    # ── Ollama ──────────────────────────────────────────────────────────────
    endpoint = f"{url}/api/chat"
    payload = {
        "model":      model,
        "messages":   messages,
        "stream":     False,
        "keep_alive": -1,
        "options":    {"num_predict": 100, "num_gpu": 99, "num_thread": 4},
    }
    if tools:
        payload["tools"] = tools

    try:
        resp = requests.post(endpoint, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        msg  = data.get("message", {})
        return {
            "content":    (msg.get("content") or "").strip(),
            "tool_calls": msg.get("tool_calls") or [],
        }
    except requests.exceptions.ConnectionError as e:
        print(f"[LLM] ConnectionError — trying to restart Ollama… ({e})")
        if ensure_ollama_running():
            try:
                resp = requests.post(endpoint, json=payload, timeout=timeout)
                resp.raise_for_status()
                data = resp.json()
                msg  = data.get("message", {})
                return {
                    "content":    (msg.get("content") or "").strip(),
                    "tool_calls": msg.get("tool_calls") or [],
                }
            except Exception:
                pass
        raise RuntimeError(
            f"Cannot connect to Ollama at {url}. "
            "Make sure Ollama is installed and run: ollama serve"
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("Ollama request timed out after 120 s.")
    except requests.exceptions.HTTPError as e:
        body = ""
        try:
            body = e.response.text[:500]
        except Exception:
            pass
        print(f"[LLM] HTTPError: {e.response.status_code} — {body}")
        raise RuntimeError(f"Ollama HTTP error: {e.response.status_code} — {body}")
    except Exception as e:
        print(f"[LLM] Unexpected error: {type(e).__name__}: {e}")
        raise RuntimeError(f"LLM call failed: {e}")


def call_llm_text(
    prompt:  str,
    system:  str | None = None,
    model:   str | None = None,
    timeout: int = 120,
) -> str:
    """
    Simple text-only generation (no tools).
    Used by planner, executor, error_handler, code_helper, dev_agent.
    """
    url, default_model = get_llm_settings()
    provider   = get_llm_provider()
    m        = model or default_model

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    if _is_openai_compatible(provider):
        endpoint, _ = get_openai_endpoints(url)
        headers = get_llm_headers()
        payload = {
            "model":      m,
            "messages":   messages,
            "stream":     False,
            "max_tokens": 2048,
        }
        try:
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            choice = resp.json().get("choices", [{}])[0]
            return (choice.get("message", {}).get("content") or "").strip()
        except Exception as e:
            raise RuntimeError(f"{provider} LLM text call failed: {e}")

    # ── Ollama ──────────────────────────────────────────────────────────────
    m = ensure_ollama_model(m)
    endpoint = f"{url}/api/chat"

    payload = {"model": m, "messages": messages, "stream": False, "keep_alive": -1, "options": {"num_predict": 300, "num_thread": 4}}

    try:
        resp = requests.post(endpoint, json=payload, timeout=timeout)
        resp.raise_for_status()
        return (resp.json().get("message", {}).get("content") or "").strip()
    except requests.exceptions.ConnectionError:
        if ensure_ollama_running():
            try:
                resp = requests.post(endpoint, json=payload, timeout=timeout)
                resp.raise_for_status()
                return (resp.json().get("message", {}).get("content") or "").strip()
            except Exception:
                pass
        raise RuntimeError(
            f"Cannot connect to Ollama at {url}. "
            "Make sure Ollama is installed and run: ollama serve"
        )
    except Exception as e:
        raise RuntimeError(f"LLM text call failed: {e}")


_SMART_PROVIDER = "openai"
_SMART_URL = "https://api.groq.com/openai/v1"
_SMART_MODEL = "llama-3.3-70b-versatile"


def call_llm_text_smart(
    prompt:  str,
    system:  str | None = None,
    timeout: int = 120,
) -> str:
    """
    Text generation using Groq's smart model (llama-3.3-70b).
    Used by tasks that need intelligence: web search summarization,
    code generation, development tasks.
    Falls back to the default model if Groq is unreachable.
    """
    cfg = _load_config()
    api_key = cfg.get("groq_api_key", "").strip() or cfg.get("llm_api_key", "").strip()
    endpoint = f"{_SMART_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": _SMART_MODEL,
        "messages": messages,
        "stream": False,
        "max_tokens": 2048,
    }

    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        choice = resp.json().get("choices", [{}])[0]
        return (choice.get("message", {}).get("content") or "").strip()
    except Exception:
        return call_llm_text(prompt, system=system, timeout=timeout)


def _parse_sse(resp: requests.Response) -> Generator[dict, None, None]:
    """Parse SSE stream from an OpenAI-compatible response."""
    full_content = ""
    buf          = ""
    tc_fragments: dict[int, dict] = {}

    for raw in resp.iter_lines():
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue

        choices = chunk.get("choices") or []
        if not choices:
            continue
        choice = choices[0]
        delta  = choice.get("delta", {})
        text   = delta.get("content") or ""

        full_content += text
        buf          += text

        while True:
            m = _SENT_END.search(buf)
            if not m:
                break
            sentence = buf[: m.start() + 1].strip()
            buf      = buf[m.end():]
            if sentence:
                yield {"type": "sentence", "text": sentence}

        for tc in (delta.get("tool_calls") or []):
            idx = tc.get("index", 0)
            if idx not in tc_fragments:
                tc_fragments[idx] = {"id": "", "function": {"name": "", "arguments": ""}}
            frag = tc_fragments[idx]
            frag["id"] = frag["id"] or tc.get("id", "")
            fn = tc.get("function", {})
            frag["function"]["name"]      += fn.get("name") or ""
            frag["function"]["arguments"] += fn.get("arguments") or ""

        finish = choice.get("finish_reason")
        if finish in ("stop", "tool_calls", "length"):
            break

    if buf.strip():
        yield {"type": "sentence", "text": buf.strip()}

    tool_calls: list = []
    for idx in sorted(tc_fragments):
        frag = tc_fragments[idx]
        args = frag["function"]["arguments"]
        tool_calls.append({
            "id":       frag["id"],
            "type":     "function",
            "function": {"name": frag["function"]["name"], "arguments": args},
        })

    yield {"type": "done", "content": full_content.strip(), "tool_calls": tool_calls}


def _stream_openai(
    messages: list,
    tools:    list | None,
    timeout:  int,
    model_override: tuple[str, str] | None = None,
) -> Generator[dict, None, None]:
    """
    Streaming backend for OpenAI-compatible servers (LM Studio, LocalAI, Jan, NVIDIA NIM, OpenRouter…).

    Parses Server-Sent Events (SSE) and accumulates streaming tool-call fragments
    so the output format is identical to the Ollama backend.
    """
    if model_override:
        provider = model_override[0]
        model = model_override[1]
        url = _PROVIDER_DEFAULTS.get(provider, ("http://localhost:11434", "qwen2.5:0.5b"))[0]
    else:
        provider = get_llm_provider()
        url, model = get_llm_settings()
    endpoint, _ = get_openai_endpoints(url)
    headers = get_llm_headers()

    payload: dict = {
        "model":      model,
        "messages":   messages,
        "stream":     True,
        "max_tokens": 2048,
    }
    if tools:
        payload["tools"]       = tools
        payload["tool_choice"] = "auto"

    try:
        with requests.post(endpoint, json=payload, headers=headers, timeout=timeout, stream=True) as resp:
            resp.raise_for_status()
            yield from _parse_sse(resp)

    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Cannot reach {provider} at {url}.\n"
            "Make sure the server is running and the URL is correct."
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(f"{provider} stream timed out.")
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code
        body = e.response.text[:300]
        if code in (413, 429):
            # 413 = payload too large, 429 = rate limited — retry on Ollama
            _fallback_ollama_url = "http://localhost:11434"
            fallback_model = "qwen2.5:0.5b"
            import copy
            slim = copy.deepcopy(payload)
            slim.pop("tools", None)
            slim.pop("tool_choice", None)
            slim["model"] = fallback_model
            fallback_endpoint = f"{_fallback_ollama_url}/api/chat"
            slim["stream"] = True
            slim["keep_alive"] = -1
            slim["options"] = {"num_predict": 100, "num_gpu": 99, "num_thread": 4}
            try:
                with requests.post(fallback_endpoint, json=slim, timeout=timeout, stream=True) as resp2:
                    resp2.raise_for_status()
                    full_content = ""
                    buf = ""
                    for raw in resp2.iter_lines():
                        if not raw:
                            continue
                        try:
                            chunk = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        msg = chunk.get("message", {})
                        text = msg.get("content") or ""
                        full_content += text
                        buf += text
                        while True:
                            m = _SENT_END.search(buf)
                            if not m:
                                break
                            sentence = buf[: m.start() + 1].strip()
                            buf = buf[m.end():]
                            if sentence:
                                yield {"type": "sentence", "text": sentence}
                        if chunk.get("done"):
                            if buf.strip():
                                yield {"type": "sentence", "text": buf.strip()}
                            yield {"type": "done", "content": full_content.strip(), "tool_calls": []}
                            return
                    if buf.strip():
                        yield {"type": "sentence", "text": buf.strip()}
                    yield {"type": "done", "content": full_content.strip(), "tool_calls": []}
            except Exception as fe:
                raise RuntimeError(f"{provider} {code} — fallback Ollama also failed: {fe}")
            return
        raise RuntimeError(f"{provider} HTTP error: {code} — {body}")
    except Exception as e:
        raise RuntimeError(f"{provider} stream failed: {e}")


def call_llm_stream(
    messages: list,
    tools:    list | None = None,
    timeout:  int | None = None,
    model_override: tuple[str, str] | None = None,
) -> Generator[dict, None, None]:
    """
    Streaming chat request.  Routes to Ollama or OpenAI-compatible backend.

    Yields:
        {"type": "sentence", "text": str}   — each complete sentence as it arrives
        {"type": "done", "content": str, "tool_calls": list}  — when stream ends

    model_override: (provider, model) to temporarily use a different backend.
    """
    if timeout is None:
        timeout = _load_config().get("llm_timeout", 300)

    _override_provider = None
    if model_override:
        _override_provider = model_override[0]

    provider = _override_provider or get_llm_provider()
    if _is_openai_compatible(provider):
        yield from _stream_openai(messages, tools, timeout, model_override)
        return

    url, model = get_llm_settings()
    model = ensure_ollama_model(model)
    endpoint   = f"{url}/api/chat"

    payload: dict = {
        "model":      model,
        "messages":   messages,
        "stream":     True,
        "keep_alive": -1,
        "options":    {"num_predict": 100, "num_gpu": 99, "num_thread": 4},
    }
    if tools:
        payload["tools"] = tools

    def _do_stream() -> Generator[dict, None, None]:
        with requests.post(endpoint, json=payload, timeout=timeout, stream=True) as resp:
            resp.raise_for_status()
            full_content = ""
            tool_calls:  list = []
            buf          = ""

            for raw in resp.iter_lines():
                if not raw:
                    continue
                try:
                    chunk = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg   = chunk.get("message", {})
                delta = msg.get("content") or ""

                full_content += delta
                buf          += delta

                # Yield complete sentences as they accumulate
                while True:
                    m = _SENT_END.search(buf)
                    if not m:
                        break
                    sentence = buf[: m.start() + 1].strip()
                    buf      = buf[m.end() :]
                    if sentence:
                        yield {"type": "sentence", "text": sentence}

                tc = msg.get("tool_calls")
                if tc:
                    tool_calls.extend(tc)

                if chunk.get("done"):
                    if buf.strip():
                        yield {"type": "sentence", "text": buf.strip()}

                    yield {
                        "type":       "done",
                        "content":    full_content.strip(),
                        "tool_calls": tool_calls,
                    }
                    return

    try:
        yield from _do_stream()
    except requests.exceptions.ConnectionError as e:
        print(f"[LLM] Stream ConnectionError — trying to restart Ollama… ({e})")
        if ensure_ollama_running():
            yield from _do_stream()
            return
        raise RuntimeError(
            f"Cannot connect to Ollama at {url}. "
            "Make sure Ollama is installed and run: ollama serve"
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("Ollama stream timed out.")
    except requests.exceptions.HTTPError as e:
        body = ""
        try:
            body = e.response.text[:500]
        except Exception:
            pass
        raise RuntimeError(f"Ollama HTTP error: {e.response.status_code} — {body}")
    except Exception as e:
        print(f"[LLM] Stream error: {type(e).__name__}: {e}")
        raise RuntimeError(f"LLM stream failed: {e}")
