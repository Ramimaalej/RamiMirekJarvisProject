import logging
import socket
from typing import Any

logger = logging.getLogger("network_discovery")


def discover_services(timeout: int = 3) -> list[dict[str, Any]]:
    devices = []
    try:
        devices.extend(_discover_zeroconf(timeout))
    except Exception as e:
        logger.warning("zeroconf discovery error: %s", e)
    try:
        devices.extend(_discover_local_ips())
    except Exception as e:
        logger.warning("local IP discovery error: %s", e)
    return devices


def _discover_zeroconf(timeout: int) -> list[dict[str, Any]]:
    try:
        from zeroconf import Zeroconf, ServiceBrowser, ServiceStateChange
    except ImportError:
        logger.info("python-zeroconf not installed — pip install zeroconf")
        return []

    results: list[dict[str, Any]] = []

    def on_service_state_change(
        zeroconf, service_type, name, state_change
    ):
        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            if info:
                results.append({
                    "name": name,
                    "type": service_type,
                    "host": info.server,
                    "address": socket.inet_ntoa(info.addresses[0]) if info.addresses else "",
                    "port": info.port,
                    "properties": {k.decode(): v.decode() if isinstance(v, bytes) else v
                                   for k, v in info.properties.items()},
                })

    services = [
        "_http._tcp.local.",
        "_https._tcp.local.",
        "_printer._tcp.local.",
        "_ipp._tcp.local.",
        "_smb._tcp.local.",
        "_airplay._tcp.local.",
        "_homekit._tcp.local.",
        "_googlecast._tcp.local.",
        "_spotify-connect._tcp.local.",
    ]

    zc = Zeroconf()
    browsers = []
    try:
        for svc in services:
            browser = ServiceBrowser(zc, svc, handlers=[on_service_state_change])
            browsers.append(browser)
        import time
        time.sleep(timeout)
    finally:
        zc.close()

    return results


def _discover_local_ips() -> list[dict[str, Any]]:
    results = []
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        results.append({
            "name": hostname,
            "type": "_local._tcp.local.",
            "host": hostname,
            "address": local_ip,
            "port": 0,
            "properties": {"hostname": hostname},
        })
    except Exception:
        pass

    try:
        import subprocess
        proc = subprocess.run(
            ["arp", "-n"],
            capture_output=True, text=True, timeout=5,
        )
        for line in proc.stdout.split("\n"):
            parts = line.split()
            if len(parts) >= 2 and parts[0].count(".") == 3:
                results.append({
                    "name": parts[1] if len(parts) > 1 else "",
                    "type": "_arp._local",
                    "host": "",
                    "address": parts[0],
                    "port": 0,
                    "properties": {},
                })
    except Exception:
        pass

    return results


def get_local_ips() -> list[str]:
    ips = []
    try:
        hostname = socket.gethostname()
        ips.append(socket.gethostbyname(hostname))
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(hostname, None):
            addr = info[4][0]
            if addr not in ips and addr.startswith(("192.", "10.", "172.")):
                ips.append(addr)
    except Exception:
        pass
    try:
        import subprocess
        proc = subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True, timeout=5
        )
        for ip in proc.stdout.strip().split():
            if ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips
