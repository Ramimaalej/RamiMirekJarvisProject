import subprocess
import logging
import json

logger = logging.getLogger(__name__)

def run_speedtest(parameters: dict | None = None, player=None) -> str:
    try:
        # Check if speedtest-cli is installed
        # Note: on user PC they might need to install it
        cmd = ["speedtest-cli", "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            # Fallback to simple ping if not installed
            return "Speedtest-cli not found. Try 'ping 8.8.8.8' instead."
        
        data = json.loads(result.stdout)
        down = data["download"] / 1_000_000
        up = data["upload"] / 1_000_000
        ping = data["ping"]
        return f"Network Speed: Download {down:.2f} Mbps, Upload {up:.2f} Mbps, Ping {ping} ms."
    except Exception as e:
        logger.error("Speedtest error: %s", e)
        return f"Speedtest failed: {str(e)}"

def get_ip_info(parameters: dict | None = None, player=None) -> str:
    import requests
    try:
        resp = requests.get("https://ipapi.co/json/", timeout=10)
        data = resp.json()
        return f"IP: {data['ip']}, City: {data['city']}, ISP: {data['org']}"
    except Exception as e:
        return f"Could not fetch IP info: {e}"
