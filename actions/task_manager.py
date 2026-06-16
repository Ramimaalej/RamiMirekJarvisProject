import json
import threading
from datetime import datetime
from pathlib import Path

TASKS_PATH = Path(__file__).resolve().parent.parent / "memory" / "tasks.json"
_lock = threading.Lock()

# ── Tasks ─────────────────────────────────────────────────────────────

def _load() -> dict:
    if not TASKS_PATH.exists():
        return {"tasks": [], "transactions": []}
    try:
        return json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"tasks": [], "transactions": []}

def _save(data: dict):
    TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASKS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def add_task(title: str, priority: str = "normal", due: str = "") -> str:
    with _lock:
        data = _load()
        task = {
            "id": f"task-{int(datetime.now().timestamp() * 1000)}",
            "title": title,
            "priority": priority if priority in ("low", "normal", "high", "critical") else "normal",
            "due": due,
            "done": False,
            "created": datetime.now().isoformat(),
        }
        data["tasks"].append(task)
        _save(data)
        return f"Task added: {title}"


def list_tasks(status: str = "") -> str:
    with _lock:
        data = _load()
        tasks = data.get("tasks", [])
    if status == "pending":
        tasks = [t for t in tasks if not t.get("done")]
    elif status == "done":
        tasks = [t for t in tasks if t.get("done")]
    if not tasks:
        return "No tasks found."
    lines = [f"Tasks ({len(tasks)}):"]
    for t in tasks:
        mark = "✓" if t.get("done") else "○"
        prio = f" [{t.get('priority', 'normal').upper()}]" if t.get("priority") and t["priority"] != "normal" else ""
        due = f" due {t['due']}" if t.get("due") else ""
        lines.append(f"  {mark} {t['title']}{prio}{due}")
    return "\n".join(lines)


def complete_task(task_id: str) -> str:
    with _lock:
        data = _load()
        for t in data["tasks"]:
            if t["id"] == task_id:
                t["done"] = True
                _save(data)
                return f"Task completed: {t['title']}"
        return f"Task not found: {task_id}"


def delete_task(task_id: str) -> str:
    with _lock:
        data = _load()
        before = len(data["tasks"])
        data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]
        if len(data["tasks"]) < before:
            _save(data)
            return "Task deleted."
        return f"Task not found: {task_id}"


def task_manager(parameters: dict = None, **kwargs) -> str:
    params = parameters or {}
    action = params.get("action", "list").strip().lower()
    if action == "add":
        title = params.get("title", "").strip()
        if not title:
            return "Please provide a task title."
        return add_task(title, params.get("priority", "normal"), params.get("due", ""))
    elif action == "complete":
        return complete_task(params.get("task_id", ""))
    elif action == "delete":
        return delete_task(params.get("task_id", ""))
    else:
        return list_tasks(params.get("status", ""))


# ── Budget Tracker ────────────────────────────────────────────────────

_CATEGORIES = {
    "food", "transport", "housing", "utilities", "entertainment",
    "health", "education", "shopping", "salary", "freelance",
    "investment", "other",
}


def add_transaction(description: str, amount: float, category: str = "other", ttype: str = "expense") -> str:
    category = category.lower()
    if category not in _CATEGORIES:
        category = "other"
    ttype = ttype.lower()
    if ttype not in ("income", "expense"):
        return "Type must be 'income' or 'expense'."
    with _lock:
        data = _load()
        tx = {
            "id": f"tx-{int(datetime.now().timestamp() * 1000)}",
            "description": description,
            "amount": amount,
            "category": category,
            "type": ttype,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "created": datetime.now().isoformat(),
        }
        data.setdefault("transactions", []).append(tx)
        _save(data)
    sign = "+" if ttype == "income" else "-"
    return f"Transaction added: {description} ({sign}${amount:.2f}, {category})"


def budget_summary(period: str = "all", category: str = "") -> str:
    with _lock:
        data = _load()
        txs = data.get("transactions", [])
    today = datetime.now().strftime("%Y-%m-%d")
    this_month = datetime.now().strftime("%Y-%m")

    if period == "month":
        txs = [t for t in txs if t.get("date", "").startswith(this_month)]
    elif period == "today":
        txs = [t for t in txs if t.get("date") == today]
    elif period == "week":
        from datetime import timedelta
        week_start = (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")
        txs = [t for t in txs if t.get("date", "") >= week_start]

    if category:
        txs = [t for t in txs if t.get("category", "").lower() == category.lower()]

    if not txs:
        return f"No transactions yet for the selected period."

    income = sum(t["amount"] for t in txs if t["type"] == "income")
    expenses = sum(t["amount"] for t in txs if t["type"] == "expense")
    period_label = {"month": "this month", "today": "today", "week": "this week", "all": "all time"}.get(period, period)

    lines = [
        f"Finance Tracker — {period_label}:",
        f"  Income:   ${income:.2f}",
        f"  Expenses: ${expenses:.2f}",
        f"  Balance:  ${income - expenses:.2f}",
    ]
    if category:
        lines.append(f"  Category filtered: {category}")
    if txs:
        lines.append("")
        lines.append("Transactions:")
        for t in txs:
            sign = "+" if t["type"] == "income" else "-"
            lines.append(f"  {t['date']} {sign}${t['amount']:.2f}  {t['description']}  [{t.get('category', 'other')}]")
    return "\n".join(lines)


def list_transactions(category: str = "", ttype: str = "") -> str:
    with _lock:
        data = _load()
        txs = data.get("transactions", [])
    if category:
        txs = [t for t in txs if t.get("category", "").lower() == category.lower()]
    if ttype:
        txs = [t for t in txs if t.get("type") == ttype]
    if not txs:
        return "No transactions found."
    lines = [f"Transactions ({len(txs)}):"]
    for t in txs:
        sign = "+" if t["type"] == "income" else "-"
        lines.append(f"  {t['date']} {sign}${t['amount']:.2f}  {t['description']}  [{t.get('category', 'other')}]")
    return "\n".join(lines)


def budget_manager(parameters: dict = None, **kwargs) -> str:
    params = parameters or {}
    action = params.get("action", "summary").strip().lower()
    if action == "add":
        try:
            amount = float(params.get("amount", 0))
        except (ValueError, TypeError):
            return "Invalid amount."
        ttype = params.get("type", "expense")
        desc = params.get("description", "").strip()
        if not desc:
            desc = "Income" if ttype == "income" else "Expense"
        return add_transaction(desc, amount, params.get("category", "other"), ttype)
    elif action == "list":
        return list_transactions(params.get("category", ""), params.get("type", ""))
    else:
        return budget_summary(params.get("period", "all"), params.get("category", ""))
