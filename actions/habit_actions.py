from __future__ import annotations

from actions.habit_tracker.database import Database
from actions.habit_tracker.habit import Habit
from actions.habit_tracker.analytics import (
    get_by_periodicity, get_by_category,
    calculate_longest_streak_all, calculate_longest_streak_habit,
    calculate_current_streak, get_completion_rate,
    get_most_struggled_habit, generate_weekly_report, generate_monthly_report,
)


def _load() -> list[Habit]:
    return Database().load_habits()


def _find(habits: list[Habit], ident: int | str) -> Habit | None:
    if isinstance(ident, int):
        return next((h for h in habits if h.id == ident), None)
    return next((h for h in habits if h.name.lower() == ident.lower()), None)


def handle(parameters: dict | None = None, player=None, **kwargs) -> str:
    if not parameters:
        return "Usage: specify an action like 'list', 'create', 'complete', 'progress', or 'report'."
    action = parameters.get("action", "list")
    db = Database()

    if action == "list":
        habits = db.load_habits()
        periodicity = parameters.get("periodicity")
        category = parameters.get("category")
        if periodicity:
            habits = get_by_periodicity(habits, periodicity)
        if category:
            habits = get_by_category(habits, category)
        if not habits:
            return "No habits found."
        lines = [f"You have {len(habits)} habit(s):"]
        for h in habits:
            streak = calculate_current_streak(h)
            lines.append(f"  #{h.id} {h.name} ({h.periodicity}, {h.category}) — {len(h.completion_dates)} done, {streak}-day streak")
        return "\n".join(lines)

    elif action == "create":
        name = parameters.get("name")
        if not name:
            return "Missing 'name' parameter."
        periodicity = parameters.get("periodicity", "daily")
        category = parameters.get("category", "general")
        try:
            habit = Habit(name, periodicity, category)
            db.save_habit(habit)
            return f"Created {periodicity} habit '{name}' (ID: {habit.id}) in category '{category}'."
        except ValueError as e:
            return str(e)

    elif action == "complete":
        ident = parameters.get("id") or parameters.get("name")
        if not ident:
            return "Missing 'id' or 'name' parameter."
        habits = db.load_habits()
        try:
            ident_int = int(ident)
        except ValueError:
            ident_int = None
        habit = _find(habits, ident_int) if ident_int else _find(habits, ident)
        if not habit:
            return f"Habit '{ident}' not found."
        habit.complete_habit()
        db.save_habit(habit)
        return f"Completed habit: {habit.name}"

    elif action == "progress":
        ident = parameters.get("id") or parameters.get("name")
        habits = db.load_habits()
        if ident:
            try:
                ident_int = int(ident)
            except ValueError:
                ident_int = None
            habit = _find(habits, ident_int) if ident_int else _find(habits, ident)
            if not habit:
                return f"Habit '{ident}' not found."
            ls = calculate_longest_streak_habit(habit)
            cs = calculate_current_streak(habit)
            cr = get_completion_rate(habit) * 100
            return (
                f"Progress for '{habit.name}':\n"
                f"  Longest streak: {ls} days\n"
                f"  Current streak: {cs} days\n"
                f"  Completion rate: {cr:.1f}%\n"
                f"  Total completions: {len(habit.completion_dates)}"
            )
        ls = calculate_longest_streak_all(habits)
        struggled = get_most_struggled_habit(habits)
        total_cr = sum(get_completion_rate(h) for h in habits)
        avg_cr = (total_cr / len(habits) * 100) if habits else 0
        lines = [f"Overall progress ({len(habits)} habits):"]
        lines.append(f"  Longest streak: {ls} days")
        lines.append(f"  Average completion rate: {avg_cr:.1f}%")
        if struggled:
            lines.append(f"  Most struggled: {struggled.name}")
        for h in habits:
            cs = calculate_current_streak(h)
            lines.append(f"  - {h.name}: {cs}-day streak, {len(h.completion_dates)} total")
        return "\n".join(lines)

    elif action == "report":
        habits = db.load_habits()
        periodicity = parameters.get("periodicity")
        category = parameters.get("category")
        if periodicity:
            habits = get_by_periodicity(habits, periodicity)
        if category:
            habits = get_by_category(habits, category)
        weekly = generate_weekly_report(habits)
        monthly = generate_monthly_report(habits)
        lines = ["Weekly report:"]
        for name, done in weekly.items():
            lines.append(f"  {name}: {'✓' if done else '✗'}")
        lines.append("Monthly report:")
        for name, done in monthly.items():
            lines.append(f"  {name}: {'✓' if done else '✗'}")
        return "\n".join(lines)

    elif action == "delete":
        ident = parameters.get("id") or parameters.get("name")
        if not ident:
            return "Missing 'id' or 'name' parameter."
        try:
            ident_int = int(ident)
            db.delete_habit(ident_int)
            return f"Deleted habit ID {ident_int}."
        except ValueError:
            habits = db.load_habits()
            habit = _find(habits, ident)
            if not habit:
                return f"Habit '{ident}' not found."
            db.delete_habit(habit.id)
            return f"Deleted habit '{habit.name}'."

    return f"Unknown action: {action}"
