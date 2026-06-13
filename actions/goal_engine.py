import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("goal_engine")

GOALS_PATH = Path(__file__).resolve().parent.parent / "memory" / "goals.json"
_lock = threading.Lock()

PHASES = ["course", "practice", "project", "review"]


def _load_goals() -> dict:
    if not GOALS_PATH.exists():
        return {"goals": []}
    try:
        return json.loads(GOALS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"goals": []}


def _save_goals(data: dict):
    GOALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOALS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _auto_phase_transition_steps(title: str, steps: list[str] | None) -> list[str]:
    if steps:
        return steps
    return [f"{p.capitalize()}: complete {title} {p}" for p in PHASES]


def create_goal(title: str, description: str = "", steps: list[str] | None = None, phased: bool = True) -> dict[str, Any]:
    with _lock:
        goals = _load_goals()
        is_auto = bool(phased and not steps)
        if is_auto:
            steps = _auto_phase_transition_steps(title, None)
        goal = {
            "id": f"goal-{int(time.time())}",
            "title": title,
            "description": description,
            "status": "active",
            "phased": is_auto,
            "progress": 0.0,
            "created": datetime.now().isoformat(),
            "steps": [{"id": f"step-{i}", "title": s, "done": False} for i, s in enumerate((steps or []))],
            "current_step": 0,
        }
        goals["goals"].append(goal)
        _save_goals(goals)
        return goal


def list_goals(status: str = "") -> list[dict[str, Any]]:
    with _lock:
        goals = _load_goals()["goals"]
        if status:
            goals = [g for g in goals if g["status"] == status]
        return goals


def get_goal(goal_id: str) -> dict[str, Any] | None:
    with _lock:
        for g in _load_goals()["goals"]:
            if g["id"] == goal_id:
                return g
    return None


def update_goal_progress(goal_id: str, step_index: int | None = None, status: str = "") -> dict[str, Any]:
    with _lock:
        goals = _load_goals()
        for g in goals["goals"]:
            if g["id"] != goal_id:
                continue

            if step_index is not None and 0 <= step_index < len(g["steps"]):
                g["steps"][step_index]["done"] = True
                g["current_step"] = step_index + 1

            done = sum(1 for s in g["steps"] if s["done"]) if g["steps"] else 0
            total = len(g["steps"]) if g["steps"] else 1
            g["progress"] = round(done / total * 100, 1)

            if status:
                g["status"] = status

            if g["progress"] >= 100:
                g["status"] = "completed"

            _save_goals(goals)
            return g
    return None


def complete_step(goal_id: str, step_title: str) -> dict[str, Any]:
    with _lock:
        goals = _load_goals()
        for g in goals["goals"]:
            if g["id"] != goal_id:
                continue
            for i, s in enumerate(g["steps"]):
                if s["title"] == step_title:
                    return update_goal_progress(goal_id, step_index=i)
    return None


def delete_goal(goal_id: str) -> bool:
    with _lock:
        goals = _load_goals()
        before = len(goals["goals"])
        goals["goals"] = [g for g in goals["goals"] if g["id"] != goal_id]
        if len(goals["goals"]) < before:
            _save_goals(goals)
            return True
    return False


def get_goal_summary() -> str:
    goals = list_goals()
    if not goals:
        return "No active goals."

    lines = [f"Goals ({len(goals)}):"]
    for g in goals:
        steps_done = sum(1 for s in g["steps"] if s["done"])
        steps_total = len(g["steps"])
        phase_info = ""
        if g.get("phased"):
            phase_info = " [auto-phased]"
        lines.append(f"  [{g['status']}] {g['title']}{phase_info} — {steps_done}/{steps_total} steps ({g['progress']}%)")
    return "\n".join(lines)


def learn_goal(title: str) -> dict[str, Any]:
    return create_goal(
        title=title,
        description=f"Learn {title} through course, practice, project, and review phases.",
        steps=None,
        phased=True,
    )
