import logging
import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("todo_display")

_MONTHS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "aout": 8, "août": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
    "decembre": 12,
}

_MONTHS_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
}

_DAYS_FR = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6}
_DAYS_EN = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}


def _load_tasks() -> list[dict]:
    from actions.task_manager import _load
    return _load().get("tasks", [])


def _generate_html(tasks: list[dict]) -> str:
    now = datetime.now()

    done_tasks = [t for t in tasks if t.get("done")]
    pending = [t for t in tasks if not t.get("done")]

    def due_class(due_str: str) -> str:
        if not due_str:
            return ""
        try:
            due = datetime.strptime(due_str, "%Y-%m-%d")
            if due < now:
                return "overdue"
            if due <= now + timedelta(days=2):
                return "soon"
        except ValueError:
            pass
        return ""

    def render_tasks(task_list: list[dict], title: str) -> str:
        if not task_list:
            return f"<h3>{title}</h3><p class='empty'>None</p>"
        rows = ""
        for t in task_list:
            prio = t.get("priority", "normal")
            due = t.get("due", "")
            dclass = due_class(due)
            prio_badge = f"<span class='prio-{prio}'>{prio}</span>" if prio != "normal" else ""
            due_str = f"<span class='due {dclass}'>{due}</span>" if due else "<span class='due none'>—</span>"
            rows += f"""
            <tr class="{dclass}">
                <td class='title'>{t['title']}</td>
                <td>{prio_badge}</td>
                <td>{due_str}</td>
            </tr>"""
        return f"<h3>{title} <span class='count'>({len(task_list)})</span></h3><table>{rows}</table>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Todo List</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: linear-gradient(135deg, #0a0a1a 0%, #1a1a3e 100%);
    color: #e0e0ff;
    padding: 24px;
    min-height: 100vh;
  }}
  h1 {{
    font-size: 28px;
    font-weight: 700;
    color: #00bfff;
    margin-bottom: 8px;
    text-shadow: 0 0 20px rgba(0, 191, 255, 0.3);
  }}
  .subtitle {{ color: #8888bb; margin-bottom: 24px; font-size: 14px; }}
  h3 {{ font-size: 18px; color: #66d9ff; margin: 20px 0 8px; }}
  .count {{ color: #8888bb; font-weight: 400; font-size: 14px; }}
  .empty {{ color: #6666aa; font-style: italic; padding: 12px; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    background: rgba(255,255,255,0.03);
    border-radius: 12px;
    overflow: hidden;
  }}
  th {{
    text-align: left;
    padding: 10px 14px;
    background: rgba(0, 191, 255, 0.1);
    color: #00bfff;
    font-weight: 600;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  td {{
    padding: 10px 14px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    font-size: 14px;
  }}
  tr:last-child td {{ border-bottom: none; }}
  .title {{ font-weight: 500; color: #ffffff; }}
  .prio-high {{ color: #ff6b6b; background: rgba(255,107,107,0.15); padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
  .prio-critical {{ color: #ff0000; background: rgba(255,0,0,0.15); padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; }}
  .prio-low {{ color: #69db7c; background: rgba(105,219,124,0.15); padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
  .due {{ font-size: 13px; }}
  .due.overdue {{ color: #ff6b6b; }}
  .due.soon {{ color: #ffd43b; }}
  .due.none {{ color: #5555aa; }}
  .done-section {{ opacity: 0.6; }}
  .done-section td.title {{ text-decoration: line-through; color: #6666aa; }}
  .stats {{
    display: flex; gap: 16px; margin: 16px 0;
  }}
  .stat-card {{
    flex: 1;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(0,191,255,0.15);
    border-radius: 10px;
    padding: 16px;
    text-align: center;
  }}
  .stat-card .num {{ font-size: 28px; font-weight: 700; color: #00bfff; }}
  .stat-card .label {{ font-size: 12px; color: #8888bb; margin-top: 4px; }}
</style>
</head>
<body>
  <h1>📋 Todo List</h1>
  <p class="subtitle">{now.strftime('%A, %B %d, %Y — %I:%M %p')}</p>
  <div class="stats">
    <div class="stat-card"><div class="num">{len(pending)}</div><div class="label">Pending</div></div>
    <div class="stat-card"><div class="num">{len(done_tasks)}</div><div class="label">Done</div></div>
    <div class="stat-card"><div class="num">{len([t for t in pending if t.get('due')])}</div><div class="label">Scheduled</div></div>
  </div>
  {render_tasks(pending, 'Pending')}
  <div class="done-section">
    {render_tasks(done_tasks, 'Completed')}
  </div>
</body>
</html>"""
    return html


def show_todo(player=None) -> str:
    tasks = _load_tasks()
    html = _generate_html(tasks)
    tmp = Path(tempfile.mktemp(suffix=".html"))
    tmp.write_text(html, encoding="utf-8")
    url = f"file://{tmp}"
    if player and hasattr(player, "open_todo_panel"):
        player.open_todo_panel(url)
        return f"📋 Showing {len(tasks)} task(s)"
    if player and hasattr(player, "open_tutor_panel"):
        player.open_tutor_panel(url)
        return f"📋 Showing {len(tasks)} task(s)"
    # fallback: return text table
    from actions.task_manager import list_tasks
    return list_tasks()


def parse_datetime(text: str) -> str:
    """Parse natural language datetime into YYYY-MM-DD string.
    Handles French and English. Examples:
    '21 aout' → 2026-08-21
    '5pm 21 august' → 2026-08-21
    'tomorrow' → 2026-06-20
    'next week' → 2026-06-27
    'in 3 days' → 2026-06-22
    """
    now = datetime.now()
    text_lower = text.lower().strip()

    # Relative: tomorrow, next week, in X days
    if re.search(r"\btomorrow\b|^demain\b", text_lower):
        return (now + timedelta(days=1)).strftime("%Y-%m-%d")
    if re.search(r"\bnext\s+week\b|^semaine\s+prochaine\b", text_lower):
        return (now + timedelta(weeks=1)).strftime("%Y-%m-%d")
    m = re.search(r"in\s+(\d+)\s+days?|dans\s+(\d+)\s+jours?", text_lower)
    if m:
        days = int(m.group(1) or m.group(2))
        return (now + timedelta(days=days)).strftime("%Y-%m-%d")

    # Try "day month" format: "21 aout", "21 august", "3 mars"
    m = re.search(r"(\d{1,2})\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|aout|août|septembre|octobre|novembre|décembre|decembre|january|february|march|april|may|june|july|august|september|october|november|december)", text_lower)
    if m:
        day = int(m.group(1))
        month_name = m.group(2)
        month = _MONTHS_FR.get(month_name) or _MONTHS_EN.get(month_name)
        if month:
            year = now.year
            return f"{year}-{month:02d}-{day:02d}"

    # Try "day/month" numeric: "21/08", "21-08"
    m = re.search(r"(\d{1,2})[/-](\d{1,2})", text_lower)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = now.year
        return f"{year}-{month:02d}-{day:02d}"

    return ""


def parse_task_text(text: str) -> dict:
    """Extract task title, due date, and priority from natural language."""
    result = {"title": text, "due": "", "priority": "normal"}

    # Extract priority
    prio_map = {"high": "high", "critical": "critical", "urgent": "critical", "low": "low", "low priority": "low"}
    for word, prio in prio_map.items():
        if word in text.lower():
            result["priority"] = prio
            result["title"] = re.sub(r'\b' + re.escape(word) + r'\b', '', result["title"], flags=re.IGNORECASE).strip()
            break

    # Extract due date
    date_str = parse_datetime(text)
    if date_str:
        result["due"] = date_str
        date_words = re.findall(r"\b\d{1,2}\s+(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|aout|août|septembre|octobre|novembre|décembre|decembre|january|february|march|april|may|june|july|august|september|october|november|december)\b|\b\d{1,2}[/-]\d{1,2}\b|\btomorrow\b|^demain\b|next\s+week|in\s+\d+\s+days?", text, re.IGNORECASE)
        for w in date_words:
            result["title"] = result["title"].replace(w, "").strip()
        result["title"] = re.sub(r'\b(due|at|by|before)\b', '', result["title"], flags=re.IGNORECASE).strip()

    # Strip remaining "priority" and "reminder" keywords from title
    result["title"] = re.sub(r'\b(priority|reminder)\b', '', result["title"], flags=re.IGNORECASE).strip()

    # Clean up title
    result["title"] = re.sub(r'\s+', ' ', result["title"]).strip().rstrip(".,!?")
    return result


def show_todo_panel(parameters: dict = None, player=None) -> str:
    return show_todo(player=player)
