import psutil
import logging

logger = logging.getLogger(__name__)

def list_processes(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    sort_by = (parameters.get("sort") or "cpu").lower()
    
    procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            procs.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
            
    if sort_by == "mem":
        procs.sort(key=lambda x: x['memory_percent'], reverse=True)
    else:
        procs.sort(key=lambda x: x['cpu_percent'], reverse=True)
        
    top = procs[:10]
    lines = [f"PID {p['pid']}: {p['name']} (CPU: {p['cpu_percent']}%, MEM: {p['memory_percent']:.1f}%)" for p in top]
    return "Top 10 Processes:\n" + "\n".join(lines)

def kill_process(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    name = (parameters.get("name") or "").lower()
    pid = parameters.get("pid")
    
    if not name and not pid:
        return "Please provide process name or PID to kill."
        
    count = 0
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if (pid and proc.info['pid'] == int(pid)) or (name and name in proc.info['name'].lower()):
                proc.kill()
                count += 1
        except Exception:
            pass
            
    return f"Killed {count} process(es) matching '{name or pid}'."
