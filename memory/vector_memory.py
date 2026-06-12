import json
import threading
import numpy as np
import requests
from datetime import datetime
from pathlib import Path
import sys

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
VEC_PATH = BASE_DIR / "memory" / "vector_store.json"
_lock = threading.Lock()

def _get_config():
    cfg_path = BASE_DIR / "config" / "api_keys.json"
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _get_provider() -> str:
    cfg = _get_config()
    raw = cfg.get("llm_provider", "ollama").strip().lower().replace(" ", "_").replace("-", "_")
    if raw in ("nvidia_nim", "nvidia"):
        return "nvidia-nim"
    if raw in ("openrouter", "open_router"):
        return "openrouter"
    if raw in ("openai", "lmstudio", "localai", "jan", "llamacpp"):
        return "openai"
    return "ollama"

def _get_embedding_url() -> str:
    cfg = _get_config()
    url = cfg.get("llm_url", "http://localhost:11434").rstrip("/")
    provider = _get_provider()
    if provider == "ollama":
        return f"{url}/api/embeddings"
    if "/v1" in url:
        return f"{url}/embeddings"
    return f"{url}/v1/embeddings"

_EMBED_MODEL = "all-minilm:l6-v2"
# Embedding model for OpenAI-compatible providers — MUST be a dedicated
# embedding model, NOT a chat model.
_OPENAI_EMBED_MODELS = {
    "nvidia-nim": "nvidia/nv-embed-qa-4",
    "openai":     "text-embedding-ada-002",
    "openrouter": "openai/text-embedding-3-small",
}

def _get_embed_headers() -> dict:
    cfg = _get_config()
    key = cfg.get("llm_api_key", "").strip()
    if key:
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    return {"Content-Type": "application/json"}

def _embed(text: str) -> list[float]:
    provider = _get_provider()
    embed_url = _get_embedding_url()
    headers = _get_embed_headers()

    if provider == "ollama":
        payload = {"model": _EMBED_MODEL, "prompt": text[:1000]}
    else:
        embed_model = _OPENAI_EMBED_MODELS.get(provider, "text-embedding-ada-002")
        payload = {
            "model": embed_model,
            "input": text[:1000],
        }
    try:
        resp = requests.post(embed_url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if provider == "ollama":
            return data.get("embedding", [])
        return data.get("data", [{}])[0].get("embedding", [])
    except Exception as e:
        print(f"[VectorMemory] Embedding failed ({provider} @ {embed_url}): {e}")
        return []

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a = np.array(a, dtype=np.float64)
    b = np.array(b, dtype=np.float64)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return float(np.dot(a, b) / norm)

def _load_store() -> dict:
    if not VEC_PATH.exists():
        return {"memories": [], "conversations": []}
    try:
        return json.loads(VEC_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"memories": [], "conversations": []}

def _save_store(store: dict) -> None:
    VEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    VEC_PATH.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")

def store_memory(text: str, category: str = "general", source: str = "conversation") -> bool:
    emb = _embed(text)
    if not emb:
        return False
    with _lock:
        store = _load_store()
        entry = {
            "id": datetime.now().timestamp(),
            "text": text[:2000],
            "category": category,
            "source": source,
            "embedding": emb,
            "created": datetime.now().isoformat(),
        }
        store["memories"].append(entry)
        _save_store(store)
        print(f"[VectorMemory] Stored ({category}): {text[:60]}...")
        return True

def search_memory(query: str, top_k: int = 5, threshold: float = 0.3) -> list[dict]:
    query_emb = _embed(query)
    if not query_emb:
        return []
    with _lock:
        store = _load_store()
        candidates = store.get("memories", [])
        scored = []
        for m in candidates:
            if not m.get("embedding"):
                continue
            sim = _cosine_similarity(query_emb, m["embedding"])
            if sim >= threshold:
                scored.append((sim, m))
        scored.sort(reverse=True, key=lambda x: x[0])
        results = [{"score": s, **{k: v for k, v in m.items() if k != "embedding"}} for s, m in scored[:top_k]]
        return results

def store_conversation(user_text: str, assistant_text: str) -> None:
    full = f"User: {user_text}\nAssistant: {assistant_text}"
    emb = _embed(full)
    if not emb:
        return
    with _lock:
        store = _load_store()
        entry = {
            "id": datetime.now().timestamp(),
            "user": user_text[:500],
            "assistant": assistant_text[:2000],
            "embedding": emb,
            "created": datetime.now().isoformat(),
        }
        store["conversations"].append(entry)
        # Keep max 200 conversations to bound size
        if len(store["conversations"]) > 200:
            store["conversations"] = store["conversations"][-200:]
        _save_store(store)

def search_conversation(query: str, top_k: int = 3, threshold: float = 0.25) -> list[dict]:
    query_emb = _embed(query)
    if not query_emb:
        return []
    with _lock:
        store = _load_store()
        candidates = store.get("conversations", [])
        scored = []
        for c in candidates:
            if not c.get("embedding"):
                continue
            sim = _cosine_similarity(query_emb, c["embedding"])
            if sim >= threshold:
                scored.append((sim, c))
        scored.sort(reverse=True, key=lambda x: x[0])
        results = [{"score": s, **{k: v for k, v in c.items() if k != "embedding"}} for s, c in scored[:top_k]]
        return results

def get_relevant_context(query: str, top_k: int = 5) -> str:
    mems = search_memory(query, top_k=top_k)
    convs = search_conversation(query, top_k=3)
    parts = []
    if mems:
        parts.append("[Relevant Memories]")
        for m in mems:
            parts.append(f"  [{m['category']}] {m['text'][:200]}")
    if convs:
        parts.append("[Related Past Conversations]")
        for c in convs:
            parts.append(f"  User: {c['user'][:100]}")
            parts.append(f"  Jarvis: {c['assistant'][:200]}")
    return "\n".join(parts) if parts else ""

def get_all_categories() -> list[str]:
    with _lock:
        store = _load_store()
        cats = set(m.get("category", "general") for m in store.get("memories", []))
        return sorted(cats)

def get_memory_count() -> int:
    with _lock:
        store = _load_store()
        return len(store.get("memories", [])) + len(store.get("conversations", []))
