import platform
import socket


def system_info(parameters: dict | None = None, player=None) -> str:
    params = parameters or {}
    query = params.get("query", "all")

    info = {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "hostname": socket.gethostname(),
        "cpu": platform.processor() or "Unknown",
        "arch": platform.machine(),
        "python": platform.python_version(),
        "node": platform.node(),
    }

    if query == "os":
        return f"Operating System: {info['os']} ({info['arch']})"
    if query == "cpu":
        return f"Processor: {info['cpu']} ({info['arch']})"
    if query == "hostname":
        return f"Hostname: {info['hostname']}"
    if query == "ram":
        try:
            import psutil
            mem = psutil.virtual_memory()
            total = mem.total / (1024**3)
            return f"RAM: {total:.1f} GB total ({mem.percent}% used)"
        except ImportError:
            return "RAM info requires psutil (`pip install psutil`)"

    lines = [
        f"OS:          {info['os']}",
        f"Arch:        {info['arch']}",
        f"Hostname:    {info['hostname']}",
        f"CPU:         {info['cpu']}",
        f"Python:      {info['python']}",
    ]
    return "\n".join(lines)
