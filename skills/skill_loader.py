import json
import os
import re
from pathlib import Path
import sys

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

SKILLS_DIR = get_base_dir() / "skills" / "definitions"
SKILLS_DIR.mkdir(parents=True, exist_ok=True)

_skills_cache: dict[str, dict] | None = None

def _load_all_skills() -> dict[str, dict]:
    global _skills_cache
    if _skills_cache is not None:
        return _skills_cache
    skills = {}
    for f in sorted(SKILLS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            name = data.get("name", f.stem)
            skills[name] = data
            print(f"[Skills] Loaded: {name}")
        except Exception as e:
            print(f"[Skills] Error loading {f.name}: {e}")
    _skills_cache = skills
    return skills

def reload_skills() -> dict[str, dict]:
    global _skills_cache
    _skills_cache = None
    return _load_all_skills()

def get_skill(name: str) -> dict | None:
    skills = _load_all_skills()
    return skills.get(name)

def get_skill_for_task(task_description: str) -> dict | None:
    skills = _load_all_skills()
    best_match = None
    best_score = 0
    task_lower = task_description.lower()
    for name, skill in skills.items():
        triggers = skill.get("triggers", [])
        score = 0
        for t in triggers:
            if isinstance(t, str):
                if t.lower() in task_lower:
                    score += 10
                if any(word in task_lower for word in t.lower().split()):
                    score += 3
            elif isinstance(t, dict):
                pattern = t.get("pattern", "")
                if pattern and re.search(pattern, task_lower):
                    score += t.get("weight", 10)
                keywords = t.get("keywords", [])
                for kw in keywords:
                    if kw.lower() in task_lower:
                        score += t.get("keyword_weight", 5)
        if score > best_score:
            best_score = score
            best_match = skill
    return best_match if best_score >= 5 else None

def list_skills() -> list[dict]:
    skills = _load_all_skills()
    return [
        {
            "name": name,
            "description": s.get("description", ""),
            "version": s.get("version", "1.0"),
            "trigger_count": len(s.get("triggers", [])),
        }
        for name, s in skills.items()
    ]

def get_active_skill_context(task_description: str) -> str:
    skill = get_skill_for_task(task_description)
    if not skill:
        return ""
    instructions = skill.get("instructions", "")
    tools = skill.get("preferred_tools", [])
    knowledge = skill.get("knowledge", "")
    parts = [f"[SKILL: {skill.get('name', 'Unknown')}]"]
    if instructions:
        parts.append(f"Instructions: {instructions}")
    if tools:
        parts.append(f"Preferred tools: {', '.join(tools)}")
    if knowledge:
        parts.append(f"Knowledge: {knowledge}")
    return "\n".join(parts)
