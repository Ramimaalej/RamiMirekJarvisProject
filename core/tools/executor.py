"""Per-tool execution logic (extracted from main.py _execute_tool)."""
from __future__ import annotations
import json
import threading
import traceback

# ── Action imports (identiques au main.py original) ──────────────────────
from actions.file_processor import file_processor
from actions.flight_finder import flight_finder
from actions.open_app import open_app
from actions.fcc_runner import run_fcc_in_folder
from actions.dashboard import (
    add_to_dashboard,
    remove_from_dashboard,
    list_dashboard,
    open_dashboard,
    log_usage as dashboard_log_usage,
)
from actions.weather_report import weather_action
from actions.maps import maps_action
from actions.stock_prices import stock_price_action
from actions.news_reader import news_action
from actions.public_apis import check_crypto, check_currency, check_time, check_quote, check_rate
from actions.opencode_launcher import opencode_action
from actions.get_datetime import get_datetime
from actions.send_message import send_message
from actions.reminder import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor import screen_process
from actions.youtube_video import youtube_video
from actions.desktop import desktop_control
from actions.browser_control import browser_control
from actions.books import book_controller
from actions.jobs import job_search_action
from actions.file_controller import file_controller
from actions.code_helper import code_helper
from actions.dev_agent import dev_agent
from actions.web_search import web_search as web_search_action
from actions.computer_control import computer_control
from actions.game_updater import game_updater
from actions.get_location import get_location
from actions.browser_use_agent import run_browser_use_task
from actions.screen_reader import get_ui_elements, get_active_window_info
from actions.face_recognition import detect_faces, analyze_camera_feed
from actions.wake_word import start_wake_word, stop_wake_word
from actions.github_integration import _get_client as _get_gh_client
from actions.github_integration import clone_and_run
from actions.file_search import search_files
from actions.finance_tracker import _get_client as _get_finance_client
from actions.network_discovery import discover_services, get_local_ips
from actions.voice_calls import _get_client as _get_lk_client
from actions.monitor_manager import get_monitors, get_monitor_summary, set_monitor_brightness, get_active_monitor
from actions.obsidian_vault import save_note, search_notes, list_notes, create_knowledge_graph, set_vault_path, get_all_tags
from actions.package_manager import install_package, uninstall_package, list_installed, update_all, detect_os_package_manager
from actions.goal_engine import create_goal, list_goals, get_goal, update_goal_progress, complete_step, delete_goal, get_goal_summary
from actions.task_manager import task_manager, budget_manager, add_task, complete_task, delete_task, list_tasks, add_transaction, list_transactions, budget_summary
from actions.screen_explain import screen_explain
from actions.screen_vision import screen_vision as screen_vision_action
import actions.device_scanner as _devices
import actions.stock_market as _stocks
import actions.translator as _trans
import actions.media_downloader as _dl
import actions.network_tools as _net
import actions.process_mgr as _proc
import actions.archive_tools as _arch
import actions.image_edit as _img
import actions.wiki_tools as _wiki
import actions.system_health as _health
import actions.news_pro as _news_pro

from actions.qr_tools import qr_generate as _qr_gen, qr_scan as _qr_scan
from actions.clipboard_mgr import clipboard_read as _clip_read, clipboard_write as _clip_write
from actions.dictionary_tools import word_definition as _word_def, word_synonyms as _word_syn, word_example as _word_ex
from actions.math_solver import solve_math as _solve_math
from actions.hash_tools import hash_string as _hash_str, hash_file as _hash_file
from actions.random_tools import dice_roll as _dice_roll, coin_flip as _coin_flip, random_pick as _rand_pick
from actions.notes_tools import quick_note_save as _note_save, quick_note_list as _note_list, quick_note_find as _note_find
from actions.system_info_tools import battery_status as _battery, disk_info as _disk_info, wifi_status as _wifi
from actions.screenshot_ocr import screen_find_text as _screen_find
from actions.comfyui import generate_image
from actions.file_converter import convert_file
from actions.random_number import random_number
from actions.system_info import system_info
from actions.unit_converter import convert_units
from actions.timer_scheduler import handle as timer_handle, set_on_fire as timer_set_callback
from actions.task_graph import create_task as tg_create_task, complete_task as tg_complete_task, get_available_tasks, get_task_graph_summary, get_critical_path, delete_task as tg_delete_task, reset_graph
from actions.security_vault import store_secret, get_secret, list_secrets, delete_secret
from actions.context_bus import get_bus, get_context, get_all_context
from actions.project_scaffold import scaffold_project
from actions.project_init import handle as project_init_handle
from actions.projectinitializer import handle as project_initializer_handle
from actions.relationship_graph import (
    add_node, remove_node, add_edge, remove_edge,
    get_related, resolve_deployment, get_graph_summary,
)
from actions.realtime_tutor import realtime_tutor, stop_tutor
from actions.email_reader import read_emails
from actions.habit_actions import handle as handle_habit
from actions.forensics import file_history, process_history, network_history, what_installed_since, get_forensics_summary
from actions.google_workspace import google_workspace_action
from actions.remote_control import remote_control
from actions.federation import federation
from actions.intent_router import route as route_intent
from actions.hermes_agent import hermes_task as hermes_agent_task

# ── Core / agent / memory / skills ───────────────────────────────────────
from agent.agent_manager import get_agent_manager
from core.scheduler import get_scheduler
from skills.skill_loader import get_active_skill_context, list_skills, reload_skills
from memory.memory_manager import load_memory, update_memory, format_memory_for_prompt
from memory.vector_memory import store_memory, store_conversation, get_relevant_context, get_memory_count, search_memory
from core.safe_math import safe_math as calculate
from core.fast_browser import FastBrowser, get_fast_browser

from gws_bridge import (
    get_unread_emails as gws_get_unread_emails,
    search_emails as gws_search_emails,
    send_email as gws_send_email,
    reply_email as gws_reply_email,
    get_todays_agenda,
    get_upcoming_events,
    create_event,
    delete_event,
    search_files as gws_search_files,
    upload_file,
    create_doc,
    create_meet,
    is_authenticated as gws_is_authenticated,
    GwsError,
)

def execute_tool(ui, name: str, args: dict,
                 speak=lambda x: None,
                 run_async=lambda c: None,
                 shutdown=lambda: None,
                 ) -> str:
    print(f"[JARVIS] 🔧 {name}  {args}")
    ui.set_state("THINKING")

    if name == "greeting":
        return args.get("response", "Hello!")

    # save_memory is handled silently
    if name == "save_memory":
        category = args.get("category", "notes")
        key      = args.get("key", "")
        value    = args.get("value", "")
        if key and value:
            # Append mode for lists — merge with existing value
            memory  = load_memory()
            existing = memory.get(category, {}).get(key, {}).get("value", "")
            if existing and category in ("notes", "preferences") and any(w in key.lower() for w in ["list", "todo", "grocery", "shopping", "tasks", "items"]):
                value = existing + "\n- " + value
                print(f"[Memory] 📋 Appended to {category}/{key}")
            update_memory({category: {key: {"value": value}}})
            print(f"[Memory] 💾 {category}/{key} = {value}")
            # Also store in vector memory for semantic search
            try:
                threading.Thread(
                    target=store_memory,
                    args=(f"{key}: {value}", category, "fact"),
                    daemon=True
                ).start()
            except Exception:
                pass
        if not ui.muted:
            ui.set_state("LISTENING")
        return "__SILENT__"

    result = "Done."
    try:
        if name == "open_app":
            r = open_app(parameters=args, response=None, player=ui)
            result = r or f"Opened {args.get('app_name')}."
            # Feed the dashboard only after an actual successful launch.
            if r and not any(word in r for word in ("Could not", "Failed", "Unsupported")):
                try:
                    dashboard_log_usage(args.get("app_name", ""))
                except Exception:
                    pass
        elif name == "list_apps":
            from actions.open_app import list_apps
            result = list_apps(args, ui)

        elif name == "run_fcc":
            r = run_fcc_in_folder(parameters=args, response=None, player=ui)
            result = r or "Free Claude Code launched."

        elif name == "open_dashboard":
            r = open_dashboard(parameters=args, response=None, player=ui)
            result = r or "Dashboard opened."

        elif name == "add_dashboard":
            apps = args.get("apps") or []
            msgs = [add_to_dashboard(a) for a in apps]
            result = " ".join(msgs) if msgs else add_to_dashboard("")

        elif name == "remove_dashboard":
            apps = args.get("apps") or []
            msgs = [remove_from_dashboard(a) for a in apps]
            result = " ".join(msgs) if msgs else remove_from_dashboard("")

        elif name == "list_dashboard":
            result = list_dashboard()

        elif name == "weather_report":
            r = weather_action(parameters=args, player=ui)
            result = r or "Weather delivered."

        elif name == "browser_control":
            r = browser_control(parameters=args, player=ui)
            result = r or "Done."

        elif name == "browser_use":
            task = args.get("task", "")
            headless = args.get("headless", True)
            max_steps = int(args.get("max_steps", 30))
            timeout = int(args.get("timeout", 180))
            result = run_browser_use_task(
                task=task, headless=headless,
                max_steps=max_steps, timeout=timeout,
            )

        elif name == "file_controller":
            r = file_controller(parameters=args, player=ui)
            result = r or "Done."

        elif name == "send_message":
            r = send_message(parameters=args, response=None, player=ui, session_memory=None)
            result = r or f"Message sent to {args.get('receiver')}."

        elif name == "reminder":
            r = reminder(parameters=args, response=None, player=ui)
            result = r or "Reminder set."

        elif name == "timer":
            r = timer_handle(parameters=args)
            result = r

        elif name == "youtube_video":
            r = youtube_video(parameters=args, response=None, player=ui)
            result = r or "Done."

        elif name == "screen_process":
            # Synchronous call — returns analysis text which the LLM can speak
            r = screen_process(parameters=args, response=None, player=ui, session_memory=None)
            result = r if isinstance(r, str) and r else "Screen analyzed."

        elif name == "screen_explain":
            r = screen_explain(parameters=args)
            result = r if isinstance(r, str) and r else "I cannot do that."

        elif name == "generate_image":
            r = generate_image(parameters=args)
            result = r if isinstance(r, str) and r else "Image generation failed."

        elif name == "computer_settings":
            r = computer_settings(parameters=args, response=None, player=ui)
            result = r or "Done."

        elif name == "desktop_control":
            r = desktop_control(parameters=args, player=ui)
            result = r or "Done."

        elif name == "code_helper":
            r = code_helper(parameters=args, player=ui, speak=speak)
            result = r or "Done."

        elif name == "dev_agent":
            r = dev_agent(parameters=args, player=ui, speak=speak)
            result = r or "Done."

        elif name == "agent_task":
            goal = args.get("goal", "")
            # Try Hermes Agent first; fall back to task queue
            try:
                r = hermes_agent_task(goal)
                result = r or "Done."
            except Exception:
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {
                    "low": TaskPriority.LOW,
                    "normal": TaskPriority.NORMAL,
                    "high": TaskPriority.HIGH,
                }
                priority = priority_map.get(
                    args.get("priority", "normal").lower(), TaskPriority.NORMAL
                )
                task_id = get_queue().submit(
                    goal=goal, priority=priority, speak=speak
                )
                result = f"Task started (ID: {task_id})."

        elif name == "web_search":
            r = web_search_action(parameters=args, player=ui)
            result = r or "Done."

        elif name == "screen_vision":
            r = screen_vision_action(args)
            result = r or "The screen is empty."
            # Tag the log so the chat panel marks it as a system note
            ui.write_log(f"Jarvis: {result[:300]}")
            result = ""  # already logged; keep TTS from double-speaking

        elif name == "file_processor":
            if not args.get("file_path") and ui.current_file:
                args["file_path"] = ui.current_file
            r = file_processor(parameters=args, player=ui, speak=speak)
            result = r or "Done."

        elif name == "computer_control":
            r = computer_control(parameters=args, player=ui)
            result = r or "Done."

        elif name == "run_command":
            r = computer_control(parameters={
                "action": "run_command",
                "command": args.get("command", args.get("text", "")),
                "timeout": int(args.get("timeout", 60)),
                "workdir": args.get("workdir"),
            }, player=ui)
            result = r or "Done."

        elif name == "run_python":
            r = computer_control(parameters={
                "action": "run_python",
                "code": args.get("code", ""),
                "timeout": int(args.get("timeout", 30)),
            }, player=ui)
            result = r or "Done."

        elif name == "game_updater":
            r = game_updater(parameters=args, player=ui, speak=speak)
            result = r or "Done."

        elif name == "flight_finder":
            r = flight_finder(parameters=args, player=ui)
            result = r or "Done."

        elif name == "calculate":
            r = calculate(parameters=args)
            result = r or "Done."

        elif name == "get_location":
            r = get_location(parameters=args, player=ui)
            if r:
                import re
                m = re.search(r'currently in ([^,]+)', r)
                if m:
                    ui.set_location(m.group(1).strip())
                else:
                    parts = r.split(".")
                    if parts:
                        ui.set_location(parts[0].replace("You are currently in ", ""))
            result = r or "Location retrieved."

        elif name == "maps":
            r = maps_action(parameters=args, player=ui)
            result = r or "Done."

        elif name == "stock_price":
            r = stock_price_action(parameters=args, player=ui)
            result = r or "Done."

        elif name == "stock_market":
            r = _stocks.get_stock_price(parameters=args, player=ui)
            result = r or "Market data is currently unavailable."

        elif name == "news":
            r = news_action(parameters=args, player=ui)
            result = r or "Done."

        elif name == "check_crypto":
            _explicit = (args.get("coin") or "").lower()
            if _explicit:
                coin = _explicit
                cur = (args.get("currency") or "usd").lower()
            else:
                _q = (args.get("query") or "").lower()
                coin = next((c for c in
                         ("bitcoin", "ethereum", "solana", "ripple", "dogecoin",
                          "cardano", "tether", "binancecoin", "litecoin",
                          "polkadot", "btc", "eth", "sol", "xrp", "doge",
                          "ada", "usdt", "bnb", "ltc", "dot")
                         if c in _q), "bitcoin")
                cur = next((cu for cu in ("eur", "usd", "gbp", "tnd") if cu in _q), "usd")
            result = check_crypto(coin, cur)
            if ui:
                ui.write_log(f"[public_apis] crypto {coin}")

        elif name == "currency_rate":
            _sym = args.get("symbol") or args.get("pair") or ""
            if _sym:
                pair = _sym.upper()
            else:
                _q = (args.get("query") or "").upper()
                import re as _re
                _m = _re.search(r"([A-Z]{3})[\s/-]?([A-Z]{3})", _q)
                pair = (_m.group(1) + _m.group(2)) if _m else "EURUSD"
            result = check_rate(pair)
            if ui:
                ui.write_log(f"[public_apis] rate {pair}")

        elif name == "check_time":
            place = (args.get("place") or args.get("query") or "Tunis").strip()
            if not place or place.lower() in ("now", "current", "actuelle", "il", "it", "est"):
                place = "Tunis"
            result = check_time(place)

        elif name == "random_quote":
            result = check_quote()

        elif name == "opencode_run":
            desc = args.get("description") or args.get("project") or args.get("query", "")
            if not desc:
                desc = "a new development project"
            result = opencode_action(parameters={"action": "run", "description": desc,
                                               "dir": args.get("dir")}, player=ui)

        elif name == "opencode_install":
            result = opencode_action(parameters={"action": "install"}, player=ui)

        elif name == "opencode_status":
            result = opencode_action(parameters={"action": "status"}, player=ui)

        elif name == "get_datetime":
            result = get_datetime(parameters=args)
            if result:
                speak(result)

        elif name == "shutdown_jarvis":
            ui.write_log("SYS: Shutdown requested.")

            def _shutdown():
                import time
                speak("Goodbye.")
                time.sleep(2.5)
                ui._win._quit_sig.emit()

            threading.Thread(target=_shutdown, daemon=True).start()
            return "Shutting down."

        elif name == "manage_agents":
            action = args.get("action", "").lower()
            agent_mgr = get_agent_manager()
            if action == "create":
                agent = agent_mgr.create_agent(
                    name=args.get("name", "Agent"),
                    goal=args.get("goal", ""),
                    instructions=args.get("instructions", ""),
                )
                interval = int(args.get("interval", 0))
                if interval > 0:
                    agent.start(interval=interval)
                result = f"Agent '{agent.name}' created (ID: {agent.agent_id}). {'Running every ' + str(interval) + 's.' if interval > 0 else 'Use manage_agents with action=start to run.'}"
            elif action == "start":
                agent = agent_mgr.get_agent(args.get("agent_id", ""))
                if agent:
                    agent.start(interval=int(args.get("interval", 0)))
                    result = f"Agent '{agent.name}' started."
                else:
                    result = "Agent not found."
            elif action == "stop":
                agent = agent_mgr.get_agent(args.get("agent_id", ""))
                if agent:
                    agent.stop()
                    result = f"Agent '{agent.name}' stopped."
                else:
                    result = "Agent not found."
            elif action == "remove":
                ok = agent_mgr.remove_agent(args.get("agent_id", ""))
                result = "Agent removed." if ok else "Agent not found."
            elif action in ("list", "status"):
                agents = agent_mgr.list_agents()
                if not agents:
                    result = "No background agents."
                else:
                    lines = [f"Background Agents ({len(agents)}):"]
                    for a in agents:
                        lines.append(f"  [{a['status']}] {a['name']} ({a['agent_id']}) — {a['goal']}")
                    result = "\n".join(lines)
            else:
                result = f"Unknown action: {action}"

        elif name == "clone_and_run":
            repo_url = args.get("repo_url") or args.get("url") or args.get("query", "")
            if not repo_url or "github.com" not in repo_url:
                # Try to extract URL from query if it's there
                import re as _re
                _m = _re.search(r'(https?://github\.com/[^\s]+)', repo_url)
                if _m:
                    repo_url = _m.group(1)
            
            if not repo_url or "github.com" not in repo_url:
                result = "Please provide a valid GitHub repository URL."
            else:
                result = clone_and_run(repo_url=repo_url, player=ui)

        elif name == "manage_scheduler":
            action = args.get("action", "").lower()
            sched = get_scheduler()
            if action == "add":
                job_id = sched.add_job(
                    name=args.get("name", "Job"),
                    command=args.get("command", ""),
                    schedule=args.get("schedule", "hourly"),
                    job_type=args.get("job_type", "shell"),
                )
                result = f"Job '{args.get('name')}' scheduled (ID: {job_id})."
            elif action == "remove":
                ok = sched.remove_job(args.get("job_id", ""))
                result = "Job removed." if ok else "Job not found."
            elif action == "list":
                jobs = sched.list_jobs()
                if not jobs:
                    result = "No scheduled jobs."
                else:
                    lines = ["Scheduled Jobs:"]
                    for j in jobs:
                        enabled = "✓" if j["enabled"] else "✗"
                        lines.append(f"  {enabled} [{j['type']}] {j['name']} — every {j['schedule']} (runs: {j['run_count']})")
                    result = "\n".join(lines)
            else:
                result = f"Unknown action: {action}"

        elif name == "manage_skills":
            action = args.get("action", "").lower()
            if action == "list":
                skills = list_skills()
                if not skills:
                    result = "No skills installed."
                else:
                    lines = ["Installed Skills:"]
                    for s in skills:
                        lines.append(f"  {s['name']} v{s['version']} — {s['description'][:80]}")
                    result = "\n".join(lines)
            elif action == "reload":
                skills = reload_skills()
                result = f"Reloaded {len(skills)} skills."
            else:
                result = f"Unknown action: {action}"

        elif name == "search_memory":
            query = args.get("query", "")
            top_k = int(args.get("top_k", 5))
            if not query:
                result = "No query provided."
            else:
                results = search_memory(query, top_k=top_k)
                if not results:
                    result = "No relevant memories found."
                else:
                    lines = [f"Found {len(results)} relevant memories:"]
                    for r in results:
                        lines.append(f"  [{r['category']}] {r['text'][:150]}")
                    result = "\n".join(lines)

        # ── Google Workspace tools ──────────────────────────────────────
        elif name == "gmail_get_unread":
            limit = int(args.get("limit", 10))
            emails = run_async(gws_get_unread_emails(limit=limit))
            if isinstance(emails, list) and emails:
                lines = [f"Unread emails ({len(emails)}):"]
                for e in emails:
                    subject = e.get("subject", e.get("Subject", "(no subject)"))
                    sender = e.get("from", e.get("From", "?"))
                    date = e.get("date", e.get("Date", ""))
                    lines.append(f"  From: {sender} | {subject} | {date}")
                result = "\n".join(lines)
            else:
                result = "No unread emails found."

        elif name == "gmail_search":
            query = args.get("query", "")
            emails = run_async(gws_search_emails(query=query))
            if isinstance(emails, list) and emails:
                lines = [f"Gmail search results ({len(emails)}):"]
                for e in emails:
                    subject = e.get("subject", e.get("Subject", "(no subject)"))
                    sender = e.get("from", e.get("From", "?"))
                    date = e.get("date", e.get("Date", ""))
                    lines.append(f"  From: {sender} | {subject} | {date}")
                result = "\n".join(lines)
            else:
                result = "No emails found matching that query."

        elif name == "gmail_send":
            to = args.get("to", "")
            subject = args.get("subject", "")
            body = args.get("body", "")
            run_async(gws_send_email(to=to, subject=subject, body=body))
            result = f"Email sent to {to}."

        elif name == "gmail_reply":
            message_id = args.get("message_id", "")
            body = args.get("body", "")
            run_async(gws_reply_email(message_id=message_id, body=body))
            result = "Reply sent."

        elif name == "calendar_agenda":
            days = int(args.get("days", 1))
            try:
                if days == 1:
                    events = run_async(get_todays_agenda())
                else:
                    events = run_async(get_upcoming_events(days=days))
            except Exception:
                events = None
            if isinstance(events, list) and events:
                lines = [f"Calendar ({'today' if days == 1 else f'next {days} days'}):"]
                for e in events:
                    summary = e.get("summary", e.get("Summary", "(no title)"))
                    start = e.get("start", e.get("Start", ""))
                    end = e.get("end", e.get("End", ""))
                    meet_link = e.get("hangoutLink", e.get("meet", ""))
                    extra = ""
                    lines.append(f"  {summary}  ({start} - {end}){extra}")
                result = "\n".join(lines)
            else:
                from actions.task_manager import task_manager
                result = task_manager({"action": "list", "status": "pending"})

        elif name == "calendar_create_event":
            title = args.get("title", "")
            date = args.get("date", "")
            time = args.get("time", "")
            duration = int(args.get("duration_minutes", 60))
            description = args.get("description", "")
            meet = args.get("meet", False)
            ev = run_async(create_event(
                title=title, date=date, time=time,
                duration_minutes=duration, description=description, meet=meet,
            ))
            result = f"Event '{title}' created on {date} at {time}."
            if meet:
                link = ev.get("hangoutLink", ev.get("meet", ""))
                if link:
                    result += f" Meet link: {link}"

        elif name == "calendar_delete_event":
            event_id = args.get("event_id", "")
            run_async(delete_event(event_id=event_id))
            result = "Event deleted."

        elif name == "drive_search":
            query = args.get("query", "")
            files = run_async(search_files(query=query))
            if isinstance(files, list) and files:
                lines = [f"Drive files ({len(files)}):"]
                for f in files:
                    fname = f.get("name", f.get("Name", "?"))
                    ftype = f.get("mimeType", "")
                    modified = f.get("modifiedTime", f.get("Modified", ""))
                    icon = "📄"
                    if "folder" in ftype: icon = "📁"
                    elif "sheet" in ftype: icon = "📊"
                    elif "doc" in ftype: icon = "📝"
                    elif "pdf" in ftype: icon = "📕"
                    lines.append(f"  {icon} {fname}  ({modified})")
                result = "\n".join(lines)
            else:
                result = "No files found."

        elif name == "drive_upload":
            local_path = args.get("local_path", "")
            folder_id = args.get("folder_id")
            run_async(upload_file(local_path=local_path, folder_id=folder_id))
            result = f"File uploaded to Drive."

        elif name == "drive_create_doc":
            title = args.get("title", "")
            content = args.get("content", "")
            doc = run_async(create_doc(title=title, content=content))
            doc_id = doc.get("documentId") or doc.get("id", "")
            result = f"Document '{title}' created. ID: {doc_id}"

        elif name == "meet_create":
            title = args.get("title", "")
            date = args.get("date", "")
            time = args.get("time", "")
            duration = int(args.get("duration_minutes", 60))
            ev = run_async(create_meet(
                title=title, date=date, time=time, duration_minutes=duration,
            ))
            result = f"Google Meet '{title}' created for {date} at {time}."
            link = ev.get("hangoutLink", ev.get("meet", ""))
            if link:
                result += f" Join: {link}"

        # ── New Feature Tools ─────────────────────────────────────────
        elif name == "screen_read":
            elems = get_ui_elements()
            if elems:
                lines = [f"Screen elements ({len(elems)}):"]
                for e in elems[:30]:
                    rect = e.get("rect") or {}
                    pos = f" [{rect.get('x',0)},{rect.get('y',0)}]" if rect else ""
                    lines.append(f"  {e['role']}: {e['name'][:80]}{pos}")
                result = "\n".join(lines)
            else:
                result = "No UI elements found (accessibility API may need permissions)."

        elif name == "active_window":
            info = get_active_window_info()
            result = f"Window: {info['title']} | App: {info['app']} | Role: {info['role']}"

        elif name == "detect_faces":
            r = analyze_camera_feed()
            if "error" in r:
                result = r["error"]
            else:
                people = r.get("people", [])
                parts = [f"Detected {r['faces']} face(s):"]
                for p in people:
                    parts.append(f"  Face at ({p['x']},{p['y']}) size {p['width']}x{p['height']}")
                if r.get("expressions", {}).get("smiling"):
                    parts.append("  Smiling: Yes")
                if r.get("expressions", {}).get("eyes_detected", 0) > 0:
                    parts.append(f"  Eyes: {r['expressions']['eyes_detected']}")
                result = "\n".join(parts)

        elif name == "wake_word":
            action = args.get("action", "start")
            if action == "start":
                model = args.get("model_name", "jarvis")
                sens = float(args.get("sensitivity", 0.5))
                result = start_wake_word(model_name=model, sensitivity=sens)
            elif action == "stop":
                result = stop_wake_word()
            else:
                result = f"Unknown wake word action: {action}"

        elif name == "github":
            action = args.get("action", "")
            gh = _get_gh_client()
            try:
                if action == "clone":
                    result = clone_and_run(args.get("repo", ""), player=ui)
                elif action == "list_repos":
                    repos = gh.list_repos(user=args.get("user"))
                    lines = [f"Repos ({len(repos)}):"]
                    for r in repos:
                        lines.append(f"  {r['full_name']} ({r['language']}) {'⭐'+str(r['stars']) if r['stars'] else ''}")
                    result = "\n".join(lines)
                elif action == "create_repo":
                    r = gh.create_repo(name=args["name"], description=args.get("description", ""), private=args.get("private", False))
                    result = f"Repo created: {r['url']}"
                elif action == "get_repo":
                    r = gh.get_repo(repo_full_name=args["repo"])
                    result = f"{r['full_name']}: {r['description']} ({r['language']}, {r['stars']}⭐)" if r else "Repo not found."
                elif action == "list_issues":
                    issues = gh.list_issues(repo_full_name=args["repo"], state=args.get("state", "open"))
                    lines = [f"Issues ({len(issues)}):"]
                    for i in issues:
                        lines.append(f"  #{i['number']} {i['title']} [{i['state']}]")
                    result = "\n".join(lines)
                elif action == "create_issue":
                    i = gh.create_issue(repo_full_name=args["repo"], title=args["name"], body=args.get("body", ""))
                    result = f"Issue #{i['number']} created: {i['url']}"
                elif action == "close_issue":
                    i = gh.close_issue(repo_full_name=args["repo"], issue_number=int(args["number"]))
                    result = f"Issue #{i['number']} closed."
                elif action == "list_prs":
                    prs = gh.list_prs(repo_full_name=args["repo"], state=args.get("state", "open"))
                    lines = [f"PRs ({len(prs)}):"]
                    for pr in prs:
                        lines.append(f"  #{pr['number']} {pr['title']} ({pr['author']})")
                    result = "\n".join(lines)
                elif action == "get_pr":
                    pr = gh.get_pr(repo_full_name=args["repo"], pr_number=int(args["number"]))
                    result = f"PR #{pr['number']}: {pr['title']} ({pr['state']}) by {pr['author']} — +{pr['additions']}/-{pr['deletions']} in {pr['changed_files']} files"
                elif action == "create_pr":
                    pr = gh.create_pr(repo_full_name=args["repo"], title=args["name"], head=args["head"], base=args.get("base", "main"), body=args.get("body", ""))
                    result = f"PR #{pr['number']} created: {pr['url']}"
                elif action == "merge_pr":
                    r = gh.merge_pr(repo_full_name=args["repo"], pr_number=int(args["number"]))
                    result = f"PR merged: {r['message']}" if r['merged'] else f"Merge failed: {r['message']}"
                elif action == "list_workflows":
                    flows = gh.list_workflows(repo_full_name=args["repo"])
                    lines = [f"Workflows ({len(flows)}):"]
                    for f in flows:
                        lines.append(f"  {f['name']} ({f['state']})")
                    result = "\n".join(lines)
                elif action == "list_runs":
                    runs = gh.list_workflow_runs(repo_full_name=args["repo"], branch=args.get("branch", ""))
                    lines = [f"Workflow runs ({len(runs)}):"]
                    for r in runs:
                        lines.append(f"  {r['name']}: {r['status']} / {r['conclusion']}")
                    result = "\n".join(lines)
                else:
                    result = f"Unknown GitHub action: {action}"
            except ImportError as e:
                result = f"PyGithub not installed: {e}"
            except ValueError as e:
                result = str(e)
            except Exception as e:
                result = f"GitHub error: {e}"

        elif name == "search_files_fast":
            query = args.get("query", "")
            root = args.get("root")
            max_results = int(args.get("max_results", 20))
            files = search_files(query=query, root=root, max_results=max_results)
            if files:
                lines = [f"Found {len(files)} files:"]
                for f in files:
                    size = f.get("size", 0)
                    size_str = f"{size/1024:.1f}KB" if size > 0 else ""
                    lines.append(f"  {f['path']} {size_str}")
                result = "\n".join(lines)
            else:
                result = "No files found matching that name."

        elif name == "finance":
            fc = _get_finance_client()
            action = args.get("action", "")
            try:
                if action == "accounts":
                    accs = fc.get_accounts()
                    lines = [f"Accounts ({len(accs)}):"]
                    for a in accs:
                        lines.append(f"  {a['name']} ({a['type']}): ${a['balance']:.2f}")
                    result = "\n".join(lines) if lines[1:] else "No accounts linked."
                elif action == "transactions":
                    txns = fc.get_transactions(
                        start_date=args.get("start_date", ""),
                        end_date=args.get("end_date", ""),
                        limit=int(args.get("limit", 50)),
                    )
                    lines = [f"Transactions ({len(txns)}):"]
                    for t in txns:
                        lines.append(f"  {t['date']} ${t['amount']:.2f} — {t['name']}")
                    result = "\n".join(lines) if lines[1:] else "No transactions."
                elif action in ("spending_summary", "summary"):
                    s = fc.get_spending_summary(days=int(args.get("days", 30)))
                    lines = [f"Spending (last {s['period_days']} days): Total ${s['total']} ({s['count']} txns)"]
                    for cat, amt in s.get("categories", {}).items():
                        lines.append(f"  {cat}: ${amt}")
                    result = "\n".join(lines)
                elif action == "balances":
                    result = getattr(fc, "get_account_balances")()
                else:
                    result = f"Unknown finance action: {action}"
            except ImportError as e:
                result = f"Plaid not installed: {e}"
            except ValueError as e:
                result = str(e)
            except Exception as e:
                result = f"Finance error: {e}"

        elif name == "network_scan":
            action = args.get("action", "discover")
            if action == "discover":
                timeout = int(args.get("timeout", 3))
                devices = discover_services(timeout=timeout)
                if devices:
                    lines = [f"Discovered {len(devices)} devices/services:"]
                    for d in devices:
                        addr = d.get("address", "")
                        name = d.get("name", "").replace("._tcp.local.", "")
                        svc = d.get("type", "").replace("._tcp.local.", "")
                        lines.append(f"  {name} ({svc}) @ {addr}")
                    result = "\n".join(lines)
                else:
                    result = "No devices discovered on network."
            elif action == "local_ips":
                ips = get_local_ips()
                result = f"Local IPs: {', '.join(ips)}" if ips else "No local IPs found."
            else:
                result = f"Unknown action: {action}"

        elif name == "voice_call":
            lk = _get_lk_client()
            action = args.get("action", "")
            try:
                if action == "create_room":
                    r = lk.create_room(room_name=args.get("room_name", "jarvis-room"))
                    result = f"Room '{r['name']}' created (SID: {r['sid']})"
                elif action == "list_rooms":
                    rooms = lk.list_rooms()
                    if rooms:
                        lines = [f"Active rooms ({len(rooms)}):"]
                        for r in rooms:
                            lines.append(f"  {r['name']} ({r['num_participants']} participants)")
                        result = "\n".join(lines)
                    else:
                        result = "No active rooms."
                elif action == "generate_token":
                    token = lk.generate_token(
                        identity=args.get("identity", "jarvis"),
                        room_name=args.get("room_name", "jarvis-room"),
                    )
                    result = f"Token: {token}"
                else:
                    result = f"Unknown action: {action}"
            except ImportError as e:
                result = f"LiveKit not installed: {e}"
            except ValueError as e:
                result = str(e)
            except Exception as e:
                result = f"LiveKit error: {e}"

        elif name == "monitors":
            action = args.get("action", "list")
            if action == "list":
                monitors = get_monitors()
                if monitors:
                    lines = [f"Monitors ({len(monitors)}):"]
                    for m in monitors:
                        p = " (Primary)" if m["is_primary"] else ""
                        lines.append(f"  {m['name']}{p}: {m['width']}x{m['height']} @ ({m['x']},{m['y']})")
                    result = "\n".join(lines)
                else:
                    result = "No monitor information available."
            elif action == "summary":
                result = get_monitor_summary()
            elif action == "active":
                m = get_active_monitor()
                result = f"Active: {m['name']} ({m['width']}x{m['height']})" if m else "No monitor info."
            elif action == "brightness":
                ok = set_monitor_brightness(
                    monitor_index=int(args.get("monitor", 0)),
                    brightness=float(args.get("brightness", 1.0)),
                )
                result = f"Brightness set to {args.get('brightness', '1.0')}" if ok else "Brightness control not supported."
            else:
                result = f"Unknown monitors action: {action}"

        # ── Obsidian Vault ────────────────────────────────────────────
        elif name == "obsidian":
            action = args.get("action", "")
            try:
                if action == "save":
                    r = save_note(
                        title=args.get("title", "Untitled"),
                        content=args.get("content", ""),
                        folder=args.get("folder", ""),
                    )
                    result = f"Note saved: {r['path']}"
                elif action == "search":
                    notes = search_notes(
                        query=args.get("query", ""),
                        max_results=int(args.get("max_results", 10)),
                    )
                    if notes:
                        lines = [f"Notes ({len(notes)}):"]
                        for n in notes:
                            lines.append(f"  {n['title']} ({n['modified'][:10]})")
                        result = "\n".join(lines)
                    else:
                        result = "No matching notes found."
                elif action == "list":
                    notes = list_notes(
                        folder=args.get("folder", ""),
                        max_results=int(args.get("max_results", 50)),
                    )
                    if notes:
                        lines = [f"Notes ({len(notes)}):"]
                        for n in notes:
                            lines.append(f"  {n['title']} ({n['modified'][:10]})")
                        result = "\n".join(lines)
                    else:
                        result = "No notes found."
                elif action == "graph":
                    g = create_knowledge_graph()
                    result = f"Knowledge graph: {g['node_count']} notes, {g['edge_count']} wiki-link edges"
                elif action == "tags":
                    tags = get_all_tags()
                    result = f"Tags ({len(tags)}): {', '.join(tags)}" if tags else "No tags found."
                elif action == "set_vault":
                    result = set_vault_path(args.get("vault_path", ""))
                else:
                    result = f"Unknown obsidian action: {action}"
            except Exception as e:
                result = f"Obsidian error: {e}"

        # ── Package Manager ───────────────────────────────────────────
        elif name == "package_manager":
            action = args.get("action", "")
            pkg = args.get("package", "")
            mgr = args.get("manager", "auto")
            try:
                if action == "install":
                    r = install_package(package=pkg, manager=mgr)
                    result = f"Installed {pkg} via {r['manager']}" if r.get("success") else f"Install failed: {r.get('output', '')}"
                elif action == "uninstall":
                    r = uninstall_package(package=pkg, manager=mgr)
                    result = f"Uninstalled {pkg}" if r.get("success") else f"Uninstall failed: {r.get('output', '')}"
                elif action == "list":
                    pkgs = list_installed(manager=mgr)
                    lines = [f"Packages via {mgr} ({len(pkgs)}):"]
                    for p in pkgs[:50]:
                        lines.append(f"  {p['name']} {p.get('version', '')}")
                    result = "\n".join(lines) if pkgs else f"No packages found via {mgr}."
                elif action == "update_all":
                    r = update_all(manager=mgr)
                    result = "Packages updated." if r.get("success") else f"Update failed: {r.get('output', '')}"
                elif action == "detect":
                    pm = detect_os_package_manager()
                    result = f"Detected package manager: {pm}"
                else:
                    result = f"Unknown package action: {action}"
            except Exception as e:
                result = f"Package manager error: {e}"

        # ── Goal Engine ───────────────────────────────────────────────
        elif name == "goals":
            action = args.get("action", "")
            try:
                if action == "create":
                    g = create_goal(
                        title=args.get("title", ""),
                        description=args.get("description", ""),
                        steps=args.get("steps", []),
                    )
                    step_count = len(g["steps"])
                    result = f"Goal '{g['title']}' created ({step_count} steps, ID: {g['id']})"
                elif action == "list":
                    goals = list_goals(status=args.get("status", ""))
                    if goals:
                        lines = [f"Goals ({len(goals)}):"]
                        for g in goals:
                            lines.append(f"  [{g['status']}] {g['title']} ({g['progress']}%)")
                        result = "\n".join(lines)
                    else:
                        result = "No goals found."
                elif action == "get":
                    g = get_goal(goal_id=args.get("goal_id", ""))
                    if g:
                        lines = [f"Goal: {g['title']} ({g['progress']}%)"]
                        for i, s in enumerate(g["steps"]):
                            mark = "✓" if s["done"] else "○"
                            lines.append(f"  {mark} {s['title']}")
                        result = "\n".join(lines)
                    else:
                        result = "Goal not found."
                elif action == "progress":
                    g = update_goal_progress(
                        goal_id=args.get("goal_id", ""),
                        step_index=int(args["step_index"]) if "step_index" in args else None,
                        status=args.get("status", ""),
                    )
                    result = f"Progress: {g['title']} at {g['progress']}%" if g else "Goal not found."
                elif action == "complete_step":
                    g = complete_step(goal_id=args.get("goal_id", ""), step_title=args.get("step_title", ""))
                    result = f"Step completed. Progress: {g['progress']}%" if g else "Goal/step not found."
                elif action == "delete":
                    ok = delete_goal(goal_id=args.get("goal_id", ""))
                    result = "Goal deleted." if ok else "Goal not found."
                elif action == "summary":
                    result = get_goal_summary()
                else:
                    result = f"Unknown goals action: {action}"
            except Exception as e:
                result = f"Goal engine error: {e}"

        # ── Task Graph ────────────────────────────────────────────────
        elif name == "task_graph":
            action = args.get("action", "")
            try:
                if action == "create":
                    t = tg_create_task(
                        task_id=args.get("task_id", ""),
                        description=args.get("description", ""),
                        depends_on=args.get("depends_on", []),
                    )
                    result = f"Task '{t['id']}' created (deps: {t.get('dependencies', [])})"
                elif action == "complete":
                    t = tg_complete_task(task_id=args.get("task_id", ""))
                    result = f"Task '{t['id']}' completed." if t.get("done") else t.get("error", "Failed")
                elif action == "available":
                    tasks = get_available_tasks()
                    if tasks:
                        lines = [f"Available tasks ({len(tasks)}):"]
                        for t in tasks:
                            lines.append(f"  {t['id']}: {t['description']}")
                        result = "\n".join(lines)
                    else:
                        result = "No available tasks (all done or waiting on dependencies)."
                elif action == "summary":
                    result = get_task_graph_summary()
                elif action == "critical_path":
                    path = get_critical_path()
                    result = f"Critical path: {' → '.join(path)}" if path else "No tasks in graph."
                elif action == "delete":
                    ok = tg_delete_task(task_id=args.get("task_id", ""))
                    result = "Task deleted." if ok else "Task not found."
                elif action == "reset":
                    reset_graph()
                    result = "Task graph reset."
                else:
                    result = f"Unknown task_graph action: {action}"
            except ImportError:
                result = "NetworkX required — pip install networkx"
            except Exception as e:
                result = f"Task graph error: {e}"

        # ── Tasks ──────────────────────────────────────────────────────
        elif name == "tasks":
            action = args.get("action", "list").strip().lower()
            try:
                if action == "add":
                    title = args.get("title", "").strip()
                    if not title:
                        result = "Please provide a task title."
                    else:
                        result = add_task(title, args.get("priority", "normal"), args.get("due", ""))
                elif action == "complete":
                    result = complete_task(args.get("task_id", ""))
                elif action == "delete":
                    result = delete_task(args.get("task_id", ""))
                else:
                    result = list_tasks(args.get("status", ""))
            except Exception as e:
                result = f"Task manager error: {e}"

        # ── Todo Display ───────────────────────────────────────────────
        elif name == "todo_display":
            from actions.todo_display import show_todo_panel
            result = show_todo_panel(parameters=args, player=ui)

        # ── Budget Tracker ──────────────────────────────────────────────
        elif name == "budget":
            action = args.get("action", "summary").strip().lower()
            try:
                if action == "add":
                    desc = args.get("description", "").strip()
                    if not desc:
                        result = "Please provide a description."
                    else:
                        result = add_transaction(desc, float(args.get("amount", 0)),
                                                 args.get("category", "other"),
                                                 args.get("type", "expense"))
                elif action == "list":
                    result = list_transactions(args.get("category", ""), args.get("type", ""))
                else:
                    result = budget_summary(args.get("period", "all"), args.get("category", ""))
            except Exception as e:
                result = f"Budget error: {e}"

        # ── Security Vault ────────────────────────────────────────────
        elif name == "vault":
            action = args.get("action", "")
            key = args.get("key", "")
            try:
                if action == "store":
                    result = store_secret(key=key, value=args.get("value", ""))
                elif action == "get":
                    val = get_secret(key=key)
                    result = f"{key}: {val}" if val else f"Secret '{key}' not found."
                elif action == "list":
                    keys = list_secrets()
                    result = f"Secrets ({len(keys)}): {', '.join(keys)}" if keys else "No secrets stored."
                elif action == "delete":
                    result = delete_secret(key=key)
                else:
                    result = f"Unknown vault action: {action}"
            except Exception as e:
                result = f"Vault error: {e}"

        # ── Context Bus ───────────────────────────────────────────────
        elif name == "context":
            action = args.get("action", "summary")
            try:
                if action == "summary":
                    result = get_bus().get_summary()
                elif action == "get":
                    val = get_context(key=args.get("key", ""))
                    result = f"{args['key']}: {val}" if val else f"Key '{args.get('key')}' not found."
                elif action == "search":
                    entries = get_bus().search(query=args.get("query", ""))
                    if entries:
                        lines = [f"Context history ({len(entries)}):"]
                        for e in entries:
                            lines.append(f"  [{e['timestamp'][:19]}] {e['key']}: {e['value']}")
                        result = "\n".join(lines)
                    else:
                        result = "No matching context entries."
                elif action == "keys":
                    ctx = get_all_context()
                    result = f"Context keys ({len(ctx)}): {', '.join(sorted(ctx.keys()))}" if ctx else "No context data."
                else:
                    result = f"Unknown context action: {action}"
            except Exception as e:
                result = f"Context bus error: {e}"

        # ── Project Scaffold ────────────────────────────────────────────
        elif name == "scaffold":
            r = scaffold_project(parameters=args, speak=speak, player=ui)
            result = r or "Project scaffolded."

        # ── Project Init ────────────────────────────────────────────────
        elif name == "project_init":
            r = project_init_handle(parameters=args)
            result = r

        # ── Project Initializer (Universal) ─────────────────────────────
        elif name == "projectinitializer":
            r = project_initializer_handle(parameters=args)
            result = r

        # ── Relationship Graph ─────────────────────────────────────────
        elif name == "relationship_graph":
            action = args.get("action", "")
            try:
                if action == "add_node":
                    props = {}
                    if args.get("properties"):
                        try:
                            props = json.loads(args["properties"])
                        except Exception:
                            props = {"note": args["properties"]}
                    n = add_node(
                        node_id=args.get("node_id", args.get("name", "").lower().replace(" ", "_")),
                        node_type=args.get("node_type", "project"),
                        name=args.get("name", ""),
                        properties=props,
                    )
                    result = f"Node '{n['name']}' ({n['type']}) created."
                elif action == "remove_node":
                    ok = remove_node(node_id=args.get("node_id", ""))
                    result = "Node removed." if ok else "Node not found."
                elif action == "add_edge":
                    e = add_edge(
                        source_id=args.get("node_id", ""),
                        target_id=args.get("target_id", ""),
                        relation=args.get("relation", ""),
                    )
                    result = f"Edge: {e['source']} → {e['target']} ({e['relation']})"
                elif action == "remove_edge":
                    ok = remove_edge(
                        source_id=args.get("node_id", ""),
                        target_id=args.get("target_id", ""),
                    )
                    result = "Edge removed." if ok else "Edge not found."
                elif action == "get_related":
                    rels = get_related(node_id=args.get("node_id", ""))
                    if rels:
                        lines = [f"Related to '{args['node_id']}':"]
                        for r in rels:
                            arrow = "→" if r["direction"] == "outbound" else "←"
                            lines.append(f"  {arrow} {r['node']['name']} ({r['relation'] or 'related'})")
                        result = "\n".join(lines)
                    else:
                        result = "No related nodes found."
                elif action == "resolve_deployment":
                    result = resolve_deployment(project_name=args.get("project", args.get("name", "")))
                elif action == "summary":
                    result = get_graph_summary()
                else:
                    result = f"Unknown relationship_graph action: {action}"
            except Exception as e:
                result = f"Relationship graph error: {e}"

        # ── Forensics ──────────────────────────────────────────────────
        elif name == "forensics":
            action = args.get("action", "summary")
            days = int(args.get("days", 1))
            try:
                if action == "files":
                    files = file_history(days=days, path=args.get("path", ""))
                    if files:
                        lines = ["Recent file changes:"]
                        for f in files[:20]:
                            lines.append(f"  [{f['modified'][:19]}] {f['name']} ({f['path'][:80]})")
                        result = "\n".join(lines)
                    else:
                        result = "No recent file changes."
                elif action == "processes":
                    procs = process_history(days=days)
                    if procs:
                        lines = [f"Top processes ({len(procs)}):"]
                        for p in procs[:20]:
                            cmd = p.get("command", p.get("name", p.get("pid", "?")))
                            lines.append(f"  PID {p['pid']}: {cmd}")
                        result = "\n".join(lines)
                    else:
                        result = "No process data."
                elif action == "network":
                    nets = network_history(days=days)
                    if nets:
                        lines = [f"Network connections ({len(nets)}):"]
                        for n in nets[:20]:
                            peer = n.get("peer", n.get("local", ""))
                            state = n.get("state", "")
                            extra = f" [{state}]" if state else ""
                            lines.append(f"  {peer}{extra}")
                        result = "\n".join(lines)
                    else:
                        result = "No network connections."
                elif action == "installed":
                    result = what_installed_since(days=days)
                elif action == "summary":
                    result = get_forensics_summary(days=days)
                else:
                    result = f"Unknown forensics action: {action}"
            except Exception as e:
                result = f"Forensics error: {e}"

        # ── Remote Control ─────────────────────────────────────────────
        elif name == "remote_control":
            result = remote_control(parameters=args, player=ui)

        # ── Federation ─────────────────────────────────────────────────
        elif name == "federation":
            result = federation(parameters=args, player=ui)

        elif name == "google_workspace":
            result = google_workspace_action(parameters=args, player=ui)

        elif name == "books":
            result = book_controller(parameters=args, player=ui)

        elif name == "jobs":
            result = job_search_action(parameters=args, player=ui)

        elif name == "realtime_tutor":
            if args.get("action") == "stop":
                result = stop_tutor()
            else:
                result = realtime_tutor(parameters=args, player=ui)

        elif name == "read_emails":
            result = read_emails(parameters=args, player=ui)

        elif name == "habit_tracker":
            result = handle_habit(parameters=args, player=ui)

        elif name == "set_timer":
            result = timer_handle(parameters=args, player=ui)

        elif name == "convert_file":
            result = convert_file(parameters=args, player=ui)

        elif name == "random_number":
            result = random_number(parameters=args, player=ui)

        elif name == "system_info":
            result = system_info(parameters=args, player=ui)

        elif name == "convert_units":
            result = convert_units(parameters=args, player=ui)

        elif name == "filesystem_query":
            from actions.file_controller import get_largest_files, get_disk_usage
            a = (args or {}).get("action", "largest")
            path = (args or {}).get("path", "home")
            count = int((args or {}).get("count", 10))
            if a == "disk_usage":
                result = get_disk_usage(path=path)
            else:
                result = get_largest_files(path=path, count=count)

        elif name == "solve_math":
            result = _solve_math(parameters=args, player=ui)
        elif name == "dice_roll":
            result = _dice_roll(parameters=args, player=ui)
        elif name == "coin_flip":
            result = _coin_flip(parameters=args, player=ui)
        elif name == "random_pick":
            result = _rand_pick(parameters=args, player=ui)
        elif name == "quick_note":
            result = _note_save(parameters=args, player=ui)
        elif name == "note_list":
            result = _note_list(parameters=args, player=ui)
        elif name == "note_find":
            result = _note_find(parameters=args, player=ui)
        elif name == "clipboard_read":
            result = _clip_read(parameters=args, player=ui)
        elif name == "clipboard_write":
            result = _clip_write(parameters=args, player=ui)
        elif name == "word_definition":
            result = _word_def(parameters=args, player=ui)
        elif name == "word_synonyms":
            result = _word_syn(parameters=args, player=ui)
        elif name == "word_example":
            result = _word_ex(parameters=args, player=ui)
        elif name == "hash_string":
            result = _hash_str(parameters=args, player=ui)
        elif name == "hash_file":
            result = _hash_file(parameters=args, player=ui)
        elif name == "qr_generate":
            result = _qr_gen(parameters=args, player=ui)
        elif name == "qr_scan":
            result = _qr_scan(parameters=args, player=ui)
        elif name == "screen_find_text":
            result = _screen_find(parameters=args, player=ui)
        elif name == "battery_status":
            result = _battery(parameters=args, player=ui)
        elif name == "disk_info":
            result = _disk_info(parameters=args, player=ui)
        elif name == "wifi_status":
            result = _wifi(parameters=args, player=ui)
        elif name == "system_info_tools":
            q = (args or {}).get("query", "").lower()
            if any(w in q for w in ["battery", "batterie", "percentage", "pourcentage", "charge"]):
                result = _battery(parameters=args, player=ui)
            elif any(w in q for w in ["disk", "disque", "space", "espace", "storage", "stockage"]):
                result = _disk_info(parameters=args, player=ui)
            elif any(w in q for w in ["wifi", "reseau", "network", "ssid", "internet"]):
                result = _wifi(parameters=args, player=ui)
            else:
                result = _battery(parameters=args, player=ui)

        elif name == "devices_scan":
            category = (args or {}).get("category", "all")
            if category == "all":
                result = _devices.list_devices(parameters=args, player=ui)
            else:
                result = _devices.device_detail(parameters=args, player=ui)
        else:
            result = "I cannot do that."
            ui.show_error_state(f"Unknown tool — {name}")

    except Exception as e:
        result = "I cannot do that."
        short = str(e)[:120]
        ui.show_error_state(f"{name} — {short}")
        traceback.print_exc()

    print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
    return result
