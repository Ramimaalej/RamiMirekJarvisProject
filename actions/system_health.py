import psutil
import platform
import logging

logger = logging.getLogger(__name__)

def get_system_health(parameters: dict | None = None, player=None) -> str:
    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        temp = "N/A"
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                temp = f"{list(temps.values())[0][0].current}°C"
        except Exception:
            pass
            
        status = "Healthy" if cpu < 80 and mem < 90 else "Under Load"
        return (f"System Health: {status}\n"
                f"- CPU Usage: {cpu}%\n"
                f"- RAM Usage: {mem}%\n"
                f"- Disk Usage: {disk}%\n"
                f"- Temperature: {temp}\n"
                f"- OS: {platform.system()} {platform.release()}")
    except Exception as e:
        return f"Could not check system health: {e}"
