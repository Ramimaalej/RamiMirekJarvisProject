import json
import logging
import os
import socket
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("federation")

MEMORY_PATH = Path(__file__).resolve().parent.parent / "memory" / "federation"
MEMORY_PATH.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()

INSTANCE_ID = socket.gethostname()


def _federation_file(instance: str) -> Path:
    return MEMORY_PATH / f"{instance}.json"


def _load_instance(instance: str) -> dict:
    fp = _federation_file(instance)
    if not fp.exists():
        return {"instance": instance, "last_seen": "", "memory": {}}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {"instance": instance, "last_seen": "", "memory": {}}


def _save_instance(instance: str, data: dict):
    with _lock:
        data["last_seen"] = datetime.now().isoformat()
        _federation_file(instance).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def share_memory(key: str, value: Any, ttl_hours: int = 0):
    entry = {
        "key": key,
        "value": value,
        "source": INSTANCE_ID,
        "timestamp": datetime.now().isoformat(),
    }
    if ttl_hours > 0:
        import time as _time
        entry["expires"] = _time.time() + (ttl_hours * 3600)
    with _lock:
        fp = MEMORY_PATH / "shared.json"
        if fp.exists():
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                data = {"shared": []}
        else:
            data = {"shared": []}
        data["shared"].append(entry)
        if len(data["shared"]) > 1000:
            data["shared"] = data["shared"][-1000:]
        fp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    _save_instance(INSTANCE_ID, {"instance": INSTANCE_ID, "memory": {key: value}})
    return f"Shared '{key}' from {INSTANCE_ID}."


def query_shared(key: str = "") -> list[dict[str, Any]]:
    fp = MEMORY_PATH / "shared.json"
    if not fp.exists():
        return []
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return []
    results = data.get("shared", [])
    if key:
        k = key.lower()
        results = [r for r in results if k in r.get("key", "").lower()]
    import time as _time
    now = _time.time()
    results = [r for r in results if "expires" not in r or r["expires"] > now]
    return results[-50:]


def register_instance(name: str = "", capabilities: list[str] | None = None):
    instance_name = name or INSTANCE_ID
    data = {
        "instance": instance_name,
        "hostname": socket.gethostname(),
        "capabilities": capabilities or [],
        "registered": datetime.now().isoformat(),
    }
    _save_instance(instance_name, data)
    return f"Instance '{instance_name}' registered."


def get_instances() -> list[dict[str, Any]]:
    instances = []
    for fp in MEMORY_PATH.glob("*.json"):
        if fp.name == "shared.json":
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            instances.append(data)
        except Exception:
            continue
    return instances


def sync_from(instance: str) -> str:
    data = _load_instance(instance)
    if not data or not data.get("memory"):
        return f"No data from instance '{instance}'."
    shared_count = 0
    for k, v in data.get("memory", {}).items():
        share_memory(k, v)
        shared_count += 1
    return f"Synced {shared_count} memories from '{instance}'."


def federation_summary() -> str:
    instances = get_instances()
    if not instances:
        return "No federation instances registered."

    fp = MEMORY_PATH / "shared.json"
    shared_count = 0
    if fp.exists():
        try:
            shared_count = len(json.loads(fp.read_text(encoding="utf-8")).get("shared", []))
        except Exception:
            pass

    lines = [f"Federation ({len(instances)} instances, {shared_count} shared items):"]
    for inst in instances:
        caps = inst.get("capabilities", [])
        caps_str = f" [{', '.join(caps[:3])}]" if caps else ""
        seen = inst.get("last_seen", "")[:19] if inst.get("last_seen") else "never"
        lines.append(f"  {inst['instance']} (last seen: {seen}){caps_str}")
    return "\n".join(lines)


def federation(
    parameters: dict[str, Any] | None = None,
    player=None,
) -> str:
    p = parameters or {}
    action = p.get("action", "status").lower()
    key = p.get("key", "")
    value = p.get("value", "")
    instance = p.get("instance", "")
    name = p.get("name", "")
    ttl = int(p.get("ttl_hours", 0))

    if action == "share":
        if not key or not value:
            return "Both key and value required to share memory."
        return share_memory(key=key, value=value, ttl_hours=ttl)

    elif action == "query":
        results = query_shared(key=key)
        if not results:
            return "No shared memories found."
        lines = [f"Shared memories ({len(results)}):"]
        for r in results[-10:]:
            lines.append(f"  [{r['source']}] {r['key']} = {str(r['value'])[:100]}")
        return "\n".join(lines)

    elif action == "register":
        return register_instance(name=name or INSTANCE_ID, capabilities=p.get("capabilities", []))

    elif action == "instances":
        instances = get_instances()
        if not instances:
            return "No registered instances."
        lines = [f"Instances ({len(instances)}):"]
        for inst in instances:
            seen = inst.get("last_seen", "")[:19] if inst.get("last_seen") else "never"
            lines.append(f"  {inst['instance']} (last seen: {seen})")
        return "\n".join(lines)

    elif action == "sync":
        if not instance:
            return "Instance name required to sync."
        return sync_from(instance=instance)

    elif action == "status":
        return federation_summary()

    return f"Unknown federation action: {action}"
