import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger("task_graph")

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None

GRAPH_PATH = Path(__file__).resolve().parent.parent / "memory" / "task_graph.json"
_lock = threading.Lock()


def _ensure_nx():
    if not HAS_NETWORKX:
        raise ImportError("NetworkX required — pip install networkx")


def create_task(task_id: str, description: str, depends_on: list[str] | None = None) -> dict[str, Any]:
    _ensure_nx()
    G = _load_graph()
    if task_id in G.nodes:
        return {"error": f"Task '{task_id}' already exists"}
    G.add_node(task_id, description=description, done=False)
    if depends_on:
        for dep in depends_on:
            if dep in G.nodes:
                G.add_edge(dep, task_id)
    _save_graph(G)
    return {"id": task_id, "dependencies": depends_on or []}


def complete_task(task_id: str) -> dict[str, Any]:
    _ensure_nx()
    G = _load_graph()
    if task_id not in G.nodes:
        return {"error": f"Task '{task_id}' not found"}
    G.nodes[task_id]["done"] = True
    _save_graph(G)
    return {"id": task_id, "done": True}


def get_available_tasks() -> list[dict[str, Any]]:
    """Return tasks whose dependencies are all done (ready to work on)."""
    _ensure_nx()
    G = _load_graph()
    available = []
    for node in G.nodes:
        if G.nodes[node].get("done"):
            continue
        deps = list(G.predecessors(node))
        if all(G.nodes[d].get("done") for d in deps):
            available.append({
                "id": node,
                "description": G.nodes[node].get("description", ""),
                "dependencies": deps,
            })
    return available


def get_task_graph_summary() -> str:
    _ensure_nx()
    G = _load_graph()
    if not G.nodes:
        return "No tasks in graph."

    lines = [f"Task Graph ({G.number_of_nodes()} tasks, {G.number_of_edges()} dependencies):"]
    for node in nx.topological_sort(G):
        status = "✓" if G.nodes[node].get("done") else "○"
        lines.append(f"  {status} {node}")
        deps = list(G.predecessors(node))
        if deps:
            lines.append(f"       depends on: {', '.join(deps)}")
    return "\n".join(lines)


def get_critical_path() -> list[str]:
    """Find the longest dependency chain (critical path)."""
    _ensure_nx()
    G = _load_graph()
    if not HAS_NETWORKX or not G.nodes:
        return []
    try:
        return nx.dag_longest_path(G)
    except Exception:
        return []


def delete_task(task_id: str) -> bool:
    _ensure_nx()
    G = _load_graph()
    if task_id not in G.nodes:
        return False
    G.remove_node(task_id)
    _save_graph(G)
    return True


def reset_graph():
    _ensure_nx()
    _save_graph(nx.DiGraph())


# ── Persistence ─────────────────────────────────────────────────────────

def _load_graph():
    _ensure_nx()
    G = nx.DiGraph()
    if not GRAPH_PATH.exists():
        return G
    try:
        data = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        G.add_nodes_from((n["id"], {k: v for k, v in n.items() if k != "id"}) for n in data.get("nodes", []))
        G.add_edges_from((e["source"], e["target"]) for e in data.get("edges", []))
    except Exception as e:
        logger.warning("Failed to load task graph: %s", e)
    return G


def _save_graph(G):
    with _lock:
        data = {
            "nodes": [{"id": n, **G.nodes[n]} for n in G.nodes],
            "edges": [{"source": u, "target": v} for u, v in G.edges],
        }
        GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
        GRAPH_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
