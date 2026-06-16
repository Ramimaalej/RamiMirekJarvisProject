import json
import logging
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("timer_scheduler")

_BASE_DIR = Path(__file__).resolve().parent.parent
_SCHED_PATH = _BASE_DIR / "memory" / "scheduled_tasks.json"
_lock = threading.Lock()

_timers: list[dict] = []
_scheduled: list[dict] = []
_running = False
_thread: threading.Thread | None = None
_on_fire: callable = None


def set_on_fire(callback: callable):
    global _on_fire
    _on_fire = callback


def _load():
    global _scheduled
    if not _SCHED_PATH.exists():
        _scheduled = []
        return
    try:
        _scheduled = json.loads(_SCHED_PATH.read_text(encoding="utf-8"))
    except Exception:
        _scheduled = []


def _save():
    _SCHED_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SCHED_PATH.write_text(json.dumps(_scheduled, indent=2), encoding="utf-8")


def _start_thread():
    global _running, _thread
    if _running:
        return
    _running = True
    _load()
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()


def _loop():
    global _timers, _scheduled, _running
    while _running:
        now = datetime.now()

        # Check in-memory timers
        fired = []
        with _lock:
            for t in _timers:
                if now >= datetime.fromisoformat(t["fire_at"]):
                    fired.append(t)
            _timers = [t for t in _timers if t not in fired]

        for t in fired:
            msg = t.get("message", "Timer done")
            action = t.get("action", "")
            logger.info("Timer fired: %s", msg)
            if _on_fire:
                try:
                    _on_fire(msg, action)
                except Exception as e:
                    logger.warning("Timer fire callback error: %s", e)

        # Check persistent scheduled tasks
        with _lock:
            sched_fired = []
            for s in _scheduled:
                if not s.get("enabled", True):
                    continue
                fire = s.get("fire_at", "")
                if fire:
                    try:
                        if now >= datetime.fromisoformat(fire):
                            sched_fired.append(s)
                    except Exception:
                        continue

        for s in sched_fired:
            action = s.get("action", "")
            params = s.get("params", {})
            logger.info("Scheduled task fired: %s", s.get("name", "Task"))
            if _on_fire:
                try:
                    _on_fire(s.get("name", "Task"), action, params)
                except Exception as e:
                    logger.warning("Scheduled task callback error: %s", e)
            if s.get("repeat", ""):
                try:
                    parts = s["repeat"].split()
                    num = int(parts[0])
                    unit = parts[1] if len(parts) > 1 else "minutes"
                    delta = {"seconds": num, "minutes": num * 60, "hours": num * 3600,
                             "days": num * 86400}.get(unit, num * 60)
                    new_fire = datetime.fromisoformat(s["fire_at"]) + timedelta(seconds=delta)
                    s["fire_at"] = new_fire.isoformat()
                except Exception:
                    s["enabled"] = False
                _save()
            else:
                with _lock:
                    _scheduled = [x for x in _scheduled if x["id"] != s.get("id", "")]
                _save()

        time.sleep(1)


def add_timer(minutes: int, message: str = "Timer done", action: str = "") -> str:
    fire_at = datetime.now() + timedelta(minutes=minutes)
    with _lock:
        tid = f"t{int(time.time() * 1000)}"
        _timers.append({
            "id": tid,
            "fire_at": fire_at.isoformat(),
            "message": message,
            "action": action,
        })
    _start_thread()
    return f"Timer set for {minutes} minute(s)."


def add_scheduled(fire_at: datetime, name: str, action: str, params: dict = None,
                  repeat: str = "") -> str:
    sid = f"s{int(time.time() * 1000)}"
    with _lock:
        _scheduled.append({
            "id": sid,
            "name": name,
            "fire_at": fire_at.isoformat(),
            "action": action,
            "params": params or {},
            "repeat": repeat,
            "enabled": True,
        })
        _save()
    _start_thread()
    return f"Task '{name}' scheduled for {fire_at.strftime('%I:%M %p')}."


def list_scheduled() -> list[dict]:
    with _lock:
        return list(_scheduled)


def remove_scheduled(task_id: str) -> bool:
    with _lock:
        before = len(_scheduled)
        _scheduled = [s for s in _scheduled if s["id"] != task_id]
        if len(_scheduled) < before:
            _save()
            return True
    return False


def list_timers() -> list[dict]:
    now = datetime.now()
    with _lock:
        return [
            {
                "id": t["id"],
                "message": t["message"],
                "action": t.get("action", ""),
                "remaining_sec": max(0, (datetime.fromisoformat(t["fire_at"]) - now).total_seconds()),
            }
            for t in _timers
        ]


def handle(parameters: dict = None, **kwargs) -> str:
    params = parameters or {}
    mode = params.get("mode", "timer").strip().lower()

    if mode == "timer":
        try:
            minutes = int(params.get("minutes", 0))
        except (ValueError, TypeError):
            return "Invalid minutes value."
        if minutes <= 0:
            return "Please specify a positive number of minutes."
        message = params.get("message", "Timer done")
        return add_timer(minutes, message)

    elif mode == "schedule":
        time_str = params.get("time", "").strip()
        action = params.get("action", "").strip()
        name = params.get("name", action or "Scheduled task")
        if not time_str or not action:
            return "Please provide both time and action."
        now = datetime.now()
        try:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            ampm = params.get("ampm", "").lower()
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            fire_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if fire_at <= now:
                fire_at += timedelta(days=1)
        except (ValueError, IndexError):
            return "Invalid time format. Use HH:MM (24h)."
        repeat = params.get("repeat", "")
        return add_scheduled(fire_at, name, action, {"action": action}, repeat)

    elif mode == "list":
        lines = []
        timers = list_timers()
        if timers:
            lines.append("Active timers:")
            for t in timers:
                sec = int(t["remaining_sec"])
                m, s = divmod(sec, 60)
                lines.append(f"  {t['message']} — {m:02d}:{s:02d} remaining")
        tasks = list_scheduled()
        if tasks:
            lines.append("Scheduled tasks:")
            for s in tasks:
                try:
                    ft = datetime.fromisoformat(s["fire_at"])
                    lines.append(f"  {s['name']} → {s.get('action', '?')} at {ft.strftime('%I:%M %p')}")
                except Exception:
                    lines.append(f"  {s['name']} → {s.get('action', '?')}")
        if not timers and not tasks:
            return "No timers or scheduled tasks."
        return "\n".join(lines)

    elif mode == "cancel":
        task_id = params.get("task_id", "")
        if task_id.startswith("t"):
            with _lock:
                before = len(_timers)
                _timers = [t for t in _timers if t["id"] != task_id]
                if len(_timers) < before:
                    return "Timer cancelled."
            return "Timer not found."
        elif remove_scheduled(task_id):
            return "Scheduled task cancelled."
        return "Task not found."

    return "Unknown mode. Use timer, schedule, list, or cancel."
