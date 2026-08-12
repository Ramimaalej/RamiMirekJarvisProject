"""Quick verification for the new run_fcc + dashboard features."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from actions.intent_router import route
from actions import fcc_runner, dashboard

PASS = 0
FAIL = 0


def check(label: str, cond: bool, extra: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {label}")
    else:
        FAIL += 1
        print(f"  ✗ {label}  {extra}")


# ── 1. Intent routing ────────────────────────────────────────────────────
print("\n[1] Intent routing")
r = route("run free claude code in jarvis")
check("run fcc in folder", r.matched and r.intent_name == "run_fcc" and r.handler_params.get("folder") == "jarvis", str(r))

r = route("run free claude code")
check("run fcc (no folder)", r.matched and r.intent_name == "run_fcc", str(r))

r = route("open free claude code in the Jarvis folder")
check("open fcc the X folder", r.matched and r.intent_name == "run_fcc" and r.handler_params.get("folder") == "Jarvis", str(r))

r = route("start fcc in ~/MyProjects/Jarvis")
check("start fcc path", r.matched and r.intent_name == "run_fcc", str(r))

r = route("open my dashboard")
check("open my dashboard", r.matched and r.intent_name == "open_dashboard", str(r))

r = route("open all my apps")
check("open all my apps", r.matched and r.intent_name == "open_dashboard", str(r))

r = route("open my daily software")
check("open daily software", r.matched and r.intent_name == "open_dashboard", str(r))

r = route("add chrome to my dashboard")
check("add chrome to dashboard", r.matched and r.intent_name == "add_dashboard" and "chrome" in (r.handler_params.get("apps") or []), str(r))

r = route("my daily software is chrome, vscode and whatsapp")
check("my daily software is X", r.matched and r.intent_name == "add_dashboard" and sorted(r.handler_params.get("apps") or []) == ["chrome", "vscode", "whatsapp"], str(r))

r = route("remove whatsapp from my dashboard")
check("remove from dashboard", r.matched and r.intent_name == "remove_dashboard" and "whatsapp" in (r.handler_params.get("apps") or []), str(r))

r = route("what is on my dashboard")
check("list dashboard", r.matched and r.intent_name == "list_dashboard", str(r))

# Make sure open_app still routes common commands
r = route("open whatsapp")
check("open whatsapp still works", r.matched and r.intent_name == "open_app", str(r))

r = route("open terminal")
check("open terminal still works", r.matched and r.intent_name == "open_app", str(r))

# ── 2. Folder finder ─────────────────────────────────────────────────────
print("\n[2] Folder finder")
jarvis = fcc_runner.find_folder("Jarvis")
check("find_folder('Jarvis')", jarvis is not None and jarvis.name.lower() == "jarvis", str(jarvis))

jarvis_path = fcc_runner.find_folder("~/MyProjects/Jarvis")
check("find_folder('~/MyProjects/Jarvis')", jarvis_path is not None and jarvis_path.name.lower() == "jarvis", str(jarvis_path))

home = fcc_runner.find_folder("~")
check("find_folder('~')", home is not None and str(home) == str(Path.home()), str(home))

# ── 3. Dashboard module ──────────────────────────────────────────────────
print("\n[3] Dashboard module")
# backup any existing dashboard file
f = dashboard.DASHBOARD_FILE
bak = None
if f.exists():
    bak = f.read_text(encoding="utf-8")

check("add_to_dashboard", "Added chrome" in dashboard.add_to_dashboard("chrome"))
check("add duplicate", "already" in dashboard.add_to_dashboard("chrome"))
check("add second app", "Added vscode" in dashboard.add_to_dashboard("vscode"))
check("list has 2", "chrome" in dashboard.list_dashboard() and "vscode" in dashboard.list_dashboard())
check("remove", "Removed chrome" in dashboard.remove_from_dashboard("chrome"))
check("list has 1", "chrome" not in dashboard.list_dashboard() and "vscode" in dashboard.list_dashboard())
check("remove empty", "Tell me which app" in dashboard.remove_from_dashboard(""))
check("remove missing", "not on your dashboard" in dashboard.remove_from_dashboard("nonexistent"))
check("log_usage no crash", dashboard.log_usage("chrome") is None)

# restore original state
if bak is not None:
    f.write_text(bak, encoding="utf-8")
else:
    f.unlink(missing_ok=True)

# ── 4. Terminal template (no launch) ─────────────────────────────────────
print("\n[4] Terminal command builder")
cmd = fcc_runner._shell_cmd(Path("/tmp/MyProj"))
check("shell cmd has fcc-server & fcc-claude",
      "fcc-server" in cmd and "fcc-claude" in cmd and "exec bash" in cmd, cmd)

print(f"\nRESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
