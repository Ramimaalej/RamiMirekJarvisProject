import json
import threading
import numpy as np
import requests
from datetime import datetime
from pathlib import Path
import sys
from core.llm_client import resolve_llm_url

_OLLAMA_URL = "http://localhost:11434"

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
VEC_PATH = BASE_DIR / "memory" / "vector_store.json"
_lock = threading.Lock()

# ── In-process vector-store cache ───────────────────────────────────────────────
# _load_store() is called for every search AND every write.  Caching by file
# mtime means repeated reads within the same turn hit RAM instead of disk.
_store_cache: dict = {"memories": [], "conversations": []}
_store_mtime: float = 0.0

def _get_config():
    cfg_path = BASE_DIR / "config" / "api_keys.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    if cfg.get("llm_url_local") or cfg.get("llm_url_remote"):
        cfg["llm_url"] = resolve_llm_url(cfg)
    return cfg

def _get_embedding_url():
    cfg = _get_config()
    if cfg.get("embed_url"):
        return cfg["embed_url"].rstrip("/")
    # Always prefer local Ollama for embeddings — all-minilm:l6-v2 is tiny (45MB)
    # and works regardless of which LLM provider is configured.
    return f"{_OLLAMA_URL}/api/embeddings"

_EMBED_MODEL = "all-minilm:l6-v2"

_embed_cache: dict[str, list[float]] = {}
_embed_warned: set[str] = set()
_embeddings_disabled: bool = False
_embed_failures: dict[str, int] = {}
_embed_lock = threading.Lock()
_EMBED_MAX_RETRIES = 3
_EMBED_RETRY_WAIT = 5.0
_EMBED_DISABLE_AFTER = 5

def _embed(text: str) -> list[float]:
    global _embeddings_disabled
    if _embeddings_disabled:
        return []

    cfg = _get_config()
    embed_url = _get_embedding_url()
    embed_model = cfg.get("embed_model") or _EMBED_MODEL
    payload = {"model": embed_model, "prompt": text[:1000]}

    failure_key = f"ollama:{embed_url}"
    with _embed_lock:
        if _embed_failures.get(failure_key, 0) >= _EMBED_DISABLE_AFTER:
            if failure_key not in _embed_warned:
                print(f"[VectorMemory] Embedding disabled after {_EMBED_DISABLE_AFTER} failures.")
                _embed_warned.add(failure_key)
            _embeddings_disabled = True
            return []

    try:
        resp = requests.post(embed_url, json=payload, timeout=3.0)
        resp.raise_for_status()
        data = resp.json()
        with _embed_lock:
            _embed_failures.pop(failure_key, None)
        return data.get("embedding", [])
    except requests.exceptions.HTTPError as e:
        with _embed_lock:
            cnt = _embed_failures.get(failure_key, 0) + 1
            _embed_failures[failure_key] = cnt
        if failure_key not in _embed_warned:
            print(f"[VectorMemory] Embedding API error ({embed_url}): {e.response.status_code} (attempt {cnt}/{_EMBED_DISABLE_AFTER})")
            _embed_warned.add(failure_key)
        return []
    except Exception as e:
        with _embed_lock:
            cnt = _embed_failures.get(failure_key, 0) + 1
            _embed_failures[failure_key] = cnt
        if failure_key not in _embed_warned:
            print(f"[VectorMemory] Embedding failed ({embed_url}): {e} (attempt {cnt}/{_EMBED_DISABLE_AFTER})")
            _embed_warned.add(failure_key)
        return []

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a = np.array(a, dtype=np.float64)
    b = np.array(b, dtype=np.float64)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return float(np.dot(a, b) / norm)

def _load_store() -> dict:
    global _store_cache, _store_mtime
    if not VEC_PATH.exists():
        return {"memories": [], "conversations": []}
    try:
        mtime = VEC_PATH.stat().st_mtime
        if mtime == _store_mtime:
            return _store_cache          # cache hit
        data = json.loads(VEC_PATH.read_text(encoding="utf-8"))
        _store_cache = data
        _store_mtime = mtime
        return _store_cache
    except Exception:
        return {"memories": [], "conversations": []}

def _invalidate_store_cache() -> None:
    """Force the next _load_store() to re-read from disk."""
    global _store_mtime
    _store_mtime = 0.0

def _save_store(store: dict) -> None:
    VEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    VEC_PATH.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")
    _invalidate_store_cache()  # next read must re-stat the file

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

def _search_memory_with_emb(query_emb: list[float], top_k: int = 5, threshold: float = 0.3) -> list[dict]:
    if not query_emb:
        return []
    with _lock:
        store = _load_store()
        scored = []
        for m in store.get("memories", []):
            if not m.get("embedding"):
                continue
            sim = _cosine_similarity(query_emb, m["embedding"])
            if sim >= threshold:
                scored.append((sim, m))
        scored.sort(reverse=True, key=lambda x: x[0])
        return [{"score": s, **{k: v for k, v in m.items() if k != "embedding"}} for s, m in scored[:top_k]]


def _search_conversation_with_emb(query_emb: list[float], top_k: int = 3, threshold: float = 0.25) -> list[dict]:
    if not query_emb:
        return []
    with _lock:
        store = _load_store()
        scored = []
        for c in store.get("conversations", []):
            if not c.get("embedding"):
                continue
            sim = _cosine_similarity(query_emb, c["embedding"])
            if sim >= threshold:
                scored.append((sim, c))
        scored.sort(reverse=True, key=lambda x: x[0])
        return [{"score": s, **{k: v for k, v in c.items() if k != "embedding"}} for s, c in scored[:top_k]]


def get_relevant_context(query: str, top_k: int = 5) -> str:
    query_emb = _embed(query)
    mems = _search_memory_with_emb(query_emb, top_k=top_k, threshold=0.3)
    convs = _search_conversation_with_emb(query_emb, top_k=3, threshold=0.25)
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
