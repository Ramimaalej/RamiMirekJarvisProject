import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable
import sys

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

AGENTS_PATH = get_base_dir() / "memory" / "agents.json"

class AgentStatus:
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"

class BackgroundAgent:
    def __init__(self, agent_id: str, name: str, goal: str, instructions: str = ""):
        self.agent_id = agent_id
        self.name = name
        self.goal = goal
        self.instructions = instructions
        self.status = AgentStatus.IDLE
        self.created = datetime.now().isoformat()
        self.last_active = self.created
        self.loop_interval: int = 0
        self.context: dict = {}
        self.result: str = ""
        self.error: str = ""
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self.on_status_change: Callable | None = None

    def start(self, interval: int = 0):
        self.status = AgentStatus.RUNNING
        self.loop_interval = interval
        self._cancel.clear()
        if interval > 0:
            self._thread = threading.Thread(target=self._loop, daemon=True)
        else:
            self._thread = threading.Thread(target=self._run_once, daemon=True)
        self._thread.start()
        if self.on_status_change:
            self.on_status_change(self.agent_id, self.status)

    def stop(self):
        self._cancel.set()
        self.status = AgentStatus.IDLE
        if self.on_status_change:
            self.on_status_change(self.agent_id, self.status)

    def cancel(self):
        self.stop()

    def _run_once(self):
        try:
            from agent.executor import AgentExecutor
            executor = AgentExecutor()
            self.result = executor.execute(
                goal=self.goal,
                speak=None,
                cancel_flag=self._cancel,
            )
            if self._cancel.is_set():
                self.status = AgentStatus.IDLE
            else:
                self.status = AgentStatus.COMPLETED
        except Exception as e:
            self.error = str(e)
            self.status = AgentStatus.FAILED
        self.last_active = datetime.now().isoformat()
        if self.on_status_change:
            self.on_status_change(self.agent_id, self.status)

    def _loop(self):
        while not self._cancel.is_set():
            try:
                from agent.executor import AgentExecutor
                executor = AgentExecutor()
                self.result = executor.execute(
                    goal=self.goal,
                    speak=None,
                    cancel_flag=self._cancel,
                )
                self.status = AgentStatus.COMPLETED if not self._cancel.is_set() else AgentStatus.IDLE
            except Exception as e:
                self.error = str(e)
                self.status = AgentStatus.FAILED
            self.last_active = datetime.now().isoformat()
            if self.on_status_change:
                self.on_status_change(self.agent_id, self.status)
            if self.loop_interval > 0:
                waited = 0
                while waited < self.loop_interval and not self._cancel.is_set():
                    time.sleep(1)
                    waited += 1
            else:
                break

    def get_state(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "goal": self.goal[:100],
            "status": self.status,
            "created": self.created,
            "last_active": self.last_active,
            "loop_interval": self.loop_interval,
            "has_result": bool(self.result),
            "has_error": bool(self.error),
        }


class AgentManager:
    def __init__(self):
        self._agents: dict[str, BackgroundAgent] = {}
        self._lock = threading.Lock()
        self._load_agents()

    def create_agent(self, name: str, goal: str, instructions: str = "") -> BackgroundAgent:
        agent_id = str(uuid.uuid4())[:8]
        agent = BackgroundAgent(agent_id, name, goal, instructions)
        with self._lock:
            self._agents[agent_id] = agent
        self._save_agents()
        return agent

    def get_agent(self, agent_id: str) -> BackgroundAgent | None:
        with self._lock:
            return self._agents.get(agent_id)

    def list_agents(self) -> list[dict]:
        with self._lock:
            return [a.get_state() for a in self._agents.values()]

    def remove_agent(self, agent_id: str) -> bool:
        with self._lock:
            agent = self._agents.get(agent_id)
            if agent:
                agent.stop()
                del self._agents[agent_id]
                self._save_agents()
                return True
            return False

    def stop_all(self):
        with self._lock:
            for agent in self._agents.values():
                agent.stop()

    def get_running_count(self) -> int:
        with self._lock:
            return sum(1 for a in self._agents.values() if a.status == AgentStatus.RUNNING)

    def _save_agents(self):
        try:
            data = []
            with self._lock:
                for a in self._agents.values():
                    data.append({
                        "agent_id": a.agent_id,
                        "name": a.name,
                        "goal": a.goal,
                        "instructions": a.instructions,
                        "status": a.status,
                        "created": a.created,
                        "last_active": a.last_active,
                        "loop_interval": a.loop_interval,
                        "context": a.context,
                    })
            AGENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            AGENTS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[AgentManager] Save failed: {e}")

    def _load_agents(self):
        if not AGENTS_PATH.exists():
            return
        try:
            data = json.loads(AGENTS_PATH.read_text(encoding="utf-8"))
            for d in data:
                agent = BackgroundAgent(d["agent_id"], d["name"], d["goal"], d.get("instructions", ""))
                agent.status = d.get("status", AgentStatus.IDLE)
                agent.created = d.get("created", datetime.now().isoformat())
                agent.last_active = d.get("last_active", agent.created)
                agent.loop_interval = d.get("loop_interval", 0)
                agent.context = d.get("context", {})
                self._agents[agent.agent_id] = agent
        except Exception as e:
            print(f"[AgentManager] Load failed: {e}")


_manager = AgentManager()

def get_agent_manager() -> AgentManager:
    return _manager
