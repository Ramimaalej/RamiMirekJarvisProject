from datetime import datetime, timedelta
from typing import List
from .habit import Habit

def get_by_periodicity(habits: List[Habit], periodicity: str) -> List[Habit]:
    return [h for h in habits if h.periodicity == periodicity]

def get_by_category(habits: List[Habit], category: str) -> List[Habit]:
    return [h for h in habits if h.category == category]

def calculate_longest_streak_all(habits: List[Habit]) -> int:
    return max((calculate_longest_streak_habit(h) for h in habits), default=0)

def calculate_longest_streak_habit(habit: Habit) -> int:
    if not habit.completion_dates:
        return 0
    dates = sorted([datetime.fromisoformat(d) for d in habit.completion_dates])
    streak = max_streak = 1
    for i in range(1, len(dates)):
        if habit.periodicity == "daily":
            delta = (dates[i].date() - dates[i-1].date()).days
        else:
            delta = dates[i].isocalendar()[1] - dates[i-1].isocalendar()[1]
        streak = streak + 1 if delta == 1 else 1
        max_streak = max(streak, max_streak)
    return max_streak

def calculate_current_streak(habit: Habit) -> int:
    if not habit.completion_dates:
        return 0
    dates = sorted([datetime.fromisoformat(d).date() for d in habit.completion_dates], reverse=True)
    today = datetime.now().date()
    delta = timedelta(days=1) if habit.periodicity == "daily" else timedelta(weeks=1)
    streak = 0
    for i, d in enumerate(dates):
        if i == 0:
            if (today - d) > delta:
                break
            streak += 1
        else:
            if (dates[i-1] - d) == delta:
                streak += 1
            else:
                break
    return streak

def get_most_struggled_habit(habits: List[Habit]) -> Habit | None:
    def missed(h):
        dates = sorted([datetime.fromisoformat(d).date() for d in h.completion_dates])
        m = 0
        for i in range(1, len(dates)):
            prev, cur = dates[i-1], dates[i]
            exp = prev + timedelta(days=1 if h.periodicity == "daily" else 7)
            if cur > exp:
                m += 1
        return m
    return max(habits, key=missed, default=None) if habits else None

def get_completion_rate(habit: Habit) -> float:
    if not habit.completion_dates:
        return 0.0
    created = datetime.fromisoformat(habit.creation_date).date()
    today = datetime.now().date()
    if habit.periodicity == "daily":
        total = (today - created).days + 1
    else:
        total = (today.isocalendar()[1] - created.isocalendar()[1]) + 1
    return len(habit.completion_dates) / total if total > 0 else 0.0

def generate_weekly_report(habits: List[Habit]) -> dict:
    week = datetime.now().date().isocalendar()[1]
    return {h.name: any(datetime.fromisoformat(d).isocalendar()[1] == week for d in h.completion_dates) for h in habits}

def generate_monthly_report(habits: List[Habit]) -> dict:
    month = datetime.now().date().month
    return {h.name: any(datetime.fromisoformat(d).month == month for d in h.completion_dates) for h in habits}
