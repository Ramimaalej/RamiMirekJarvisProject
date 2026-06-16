import json
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
import sys
import re

from core.workflows import schedule_flow

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

SCHED_PATH = get_base_dir() / "memory" / "scheduler.json"

class Scheduler:
    def __init__(self):
        self._jobs: list[dict] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._on_execute: Callable | None = None

    def set_executor(self, fn: Callable):
        self._on_execute = fn

    def start(self):
        if self._running:
            return
        self._running = True
        self._load_jobs()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[Scheduler] Started")

    def stop(self):
        self._running = False

    def add_job(self, name: str, command: str, schedule: str, job_type: str = "shell") -> str:
        import uuid
        job_id = str(uuid.uuid4())[:8]
        with self._lock:
            job = {
                "id": job_id,
                "name": name,
                "command": command,
                "schedule": schedule,
                "type": job_type,
                "enabled": True,
                "last_run": None,
                "next_run": self._parse_schedule(schedule),
                "run_count": 0,
            }
            self._jobs.append(job)
            self._save_jobs()
        return job_id

    def remove_job(self, job_id: str) -> bool:
        with self._lock:
            for i, j in enumerate(self._jobs):
                if j["id"] == job_id:
                    self._jobs.pop(i)
                    self._save_jobs()
                    return True
            return False

    def list_jobs(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "id": j["id"],
                    "name": j["name"],
                    "schedule": j["schedule"],
                    "type": j["type"],
                    "enabled": j["enabled"],
                    "last_run": j["last_run"],
                    "next_run": j["next_run"],
                    "run_count": j["run_count"],
                }
                for j in self._jobs
            ]

    def _parse_schedule(self, schedule: str) -> str:
        now = datetime.now()
        s = schedule.lower().strip()
        # Shorthand: "5m", "2h", "30s", "7d"
        m = re.match(r"^(\d+)\s*(s|sec|m|min|h|hr|d|day)s?$", s)
        if m:
            num = int(m.group(1))
            unit = m.group(2)
            mult = {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hr": 3600, "d": 86400, "day": 86400}
            seconds = num * mult.get(unit, 60)
            return (now + timedelta(seconds=seconds)).isoformat()
        # "every N seconds/minutes/hours/days"
        m = re.match(r"every\s+(\d+)\s*(second|minute|hour|day)s?", s)
        if m:
            num = int(m.group(1))
            unit = m.group(2)
            deltas = {"second": timedelta(seconds=num), "minute": timedelta(minutes=num),
                      "hour": timedelta(hours=num), "day": timedelta(days=num)}
            return (now + deltas.get(unit, timedelta(hours=1))).isoformat()
        # "daily at HH:MM" or "daily"
        m = re.match(r"daily\s*(?:at\s+(\d{1,2}):?(\d{2})?)?", s)
        if m:
            hour = int(m.group(1)) if m.group(1) else 0
            minute = int(m.group(2)) if m.group(2) else 0
            nxt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if nxt <= now:
                nxt += timedelta(days=1)
            return nxt.isoformat()
        if s in ("hourly", "every hour"):
            nxt = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            return nxt.isoformat()
        if s in ("every minute", "every 1 minute", "1m"):
            return (now + timedelta(minutes=1)).isoformat()
        return (now + timedelta(hours=1)).isoformat()

    def _loop(self):
        while self._running:
            now = datetime.now()
            to_run = []
            with self._lock:
                for job in self._jobs:
                    if not job["enabled"]:
                        continue
                    if job["next_run"] and now >= datetime.fromisoformat(job["next_run"]):
                        to_run.append(job)
            for job in to_run:
                self._execute(job)
            time.sleep(5)

    @schedule_flow(name="Scheduled Job")
    def _execute(self, job: dict):
        print(f"[Scheduler] Running: {job['name']}")
        try:
            if self._on_execute:
                self._on_execute(job["name"], job["command"], job["type"])
            with self._lock:
                for j in self._jobs:
                    if j["id"] == job["id"]:
                        j["last_run"] = datetime.now().isoformat()
                        j["run_count"] = j.get("run_count", 0) + 1
                        j["next_run"] = self._parse_schedule(j["schedule"])
                        self._save_jobs()
                        break
        except Exception as e:
            print(f"[Scheduler] Job failed: {e}")

    def _save_jobs(self):
        try:
            SCHED_PATH.parent.mkdir(parents=True, exist_ok=True)
            SCHED_PATH.write_text(json.dumps(self._jobs, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[Scheduler] Save failed: {e}")

    def _load_jobs(self):
        if not SCHED_PATH.exists():
            return
        try:
            data = json.loads(SCHED_PATH.read_text(encoding="utf-8"))
            with self._lock:
                self._jobs = data
        except Exception as e:
            print(f"[Scheduler] Load failed: {e}")


_scheduler = Scheduler()

def get_scheduler() -> Scheduler:
    return _scheduler
