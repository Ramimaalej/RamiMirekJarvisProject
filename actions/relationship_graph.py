import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("relationship_graph")

GRAPH_PATH = Path(__file__).resolve().parent.parent / "memory" / "relationship_graph.json"
_lock = threading.Lock()

NODE_TYPES = ["project", "repository", "server", "database", "credentials"]

EDGE_TYPES = {
    "project": ["repository"],
    "repository": ["server"],
    "server": ["database", "project"],
    "database": ["credentials", "server"],
    "credentials": ["database", "server"],
}


def _load_graph() -> dict:
    if not GRAPH_PATH.exists():
        return {"nodes": {}, "edges": []}
    try:
        return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"nodes": {}, "edges": []}


def _save_graph(data: dict):
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def add_node(node_id: str, node_type: str, name: str, properties: dict[str, Any] | None = None) -> dict[str, Any]:
    if node_type not in NODE_TYPES:
        raise ValueError(f"Invalid node type: {node_type}. Must be one of {NODE_TYPES}")
    with _lock:
        graph = _load_graph()
        node = {
            "id": node_id,
            "type": node_type,
            "name": name,
            "properties": properties or {},
            "created": datetime.now().isoformat(),
        }
        graph["nodes"][node_id] = node
        _save_graph(graph)
        return node


def remove_node(node_id: str) -> bool:
    with _lock:
        graph = _load_graph()
        if node_id not in graph["nodes"]:
            return False
        del graph["nodes"][node_id]
        graph["edges"] = [e for e in graph["edges"] if e["source"] != node_id and e["target"] != node_id]
        _save_graph(graph)
        return True


def add_edge(source_id: str, target_id: str, relation: str = "") -> dict[str, Any]:
    with _lock:
        graph = _load_graph()
        if source_id not in graph["nodes"]:
            raise ValueError(f"Source node '{source_id}' not found.")
        if target_id not in graph["nodes"]:
            raise ValueError(f"Target node '{target_id}' not found.")
        edge = {
            "source": source_id,
            "target": target_id,
            "relation": relation,
            "created": datetime.now().isoformat(),
        }
        graph["edges"].append(edge)
        _save_graph(graph)
        return edge


def remove_edge(source_id: str, target_id: str) -> bool:
    with _lock:
        graph = _load_graph()
        before = len(graph["edges"])
        graph["edges"] = [e for e in graph["edges"] if not (e["source"] == source_id and e["target"] == target_id)]
        if len(graph["edges"]) < before:
            _save_graph(graph)
            return True
        return False


def get_related(node_id: str, relation: str = "") -> list[dict[str, Any]]:
    graph = _load_graph()
    results = []
    for edge in graph["edges"]:
        if edge["source"] == node_id:
            if not relation or edge["relation"] == relation:
                target = graph["nodes"].get(edge["target"])
                if target:
                    results.append({"node": target, "relation": edge["relation"], "direction": "outbound"})
        elif edge["target"] == node_id:
            if not relation or edge["relation"] == relation:
                source = graph["nodes"].get(edge["source"])
                if source:
                    results.append({"node": source, "relation": edge["relation"], "direction": "inbound"})
    return results


def resolve_deployment(project_name: str) -> str:
    graph = _load_graph()
    nodes = graph["nodes"]
    edges = graph["edges"]

    project_node = None
    for nid, n in nodes.items():
        if n["type"] == "project" and (project_name.lower() in n["name"].lower() or project_name.lower() in nid.lower()):
            project_node = nid
            break
    if not project_node:
        for nid, n in nodes.items():
            if project_name.lower() in n["name"].lower():
                project_node = nid
                break
    if not project_node:
        return f"No project found matching '{project_name}'."

    chain = [nodes[project_node]["name"]]
    current = project_node

    def _follow(source: str, target_type: str) -> str | None:
        for e in edges:
            if e["source"] == source:
                t = nodes.get(e["target"])
                if t and t["type"] == target_type:
                    return e["target"]
        return None

    repo = _follow(current, "repository")
    if repo:
        repo_node = nodes[repo]
        chain.append(f"Repository: {repo_node['name']}")
        if repo_node["properties"].get("url"):
            chain[-1] += f" ({repo_node['properties']['url']})"
        server = _follow(repo, "server")
        if server:
            srv = nodes[server]
            chain.append(f"Server: {srv['name']}")
            if srv["properties"].get("url") or srv["properties"].get("ip"):
                chain[-1] += f" ({srv['properties'].get('url', srv['properties'].get('ip', ''))})"
            db = _follow(server, "database")
            if db:
                db_node = nodes[db]
                chain.append(f"Database: {db_node['name']}")
                if db_node["properties"].get("engine"):
                    chain[-1] += f" ({db_node['properties']['engine']})"
                creds = _follow(db, "credentials")
                if creds:
                    c = nodes[creds]
                    chain.append(f"Credentials: {c['name']}")
                    if c["properties"].get("username"):
                        chain[-1] += f" (user: {c['properties']['username']})"

    return "\n  → ".join(chain)


def get_graph_summary() -> str:
    graph = _load_graph()
    nodes = graph["nodes"]
    edges = graph["edges"]

    if not nodes:
        return "Empty relationship graph."

    lines = [f"Relationship Graph ({len(nodes)} nodes, {len(edges)} edges):"]
    for nid, n in sorted(nodes.items()):
        props = n.get("properties", {})
        prop_str = ""
        if props.get("url"):
            prop_str = f" — {props['url']}"
        elif props.get("ip"):
            prop_str = f" — {props['ip']}"
        elif props.get("engine"):
            prop_str = f" — {props['engine']}"
        lines.append(f"  [{n['type']}] {n['name']}{prop_str}")
        rels = get_related(nid)
        for r in rels:
            label = r["relation"] if r["relation"] else "related"
            arrow = "→" if r["direction"] == "outbound" else "←"
            lines.append(f"    {arrow} {label}: {r['node']['name']}")

    return "\n".join(lines)
