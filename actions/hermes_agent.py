import subprocess
from pathlib import Path

_HERMES_BIN: str | None = None

def _find_hermes() -> str | None:
    candidates = ["hermes", str(Path.home() / ".local" / "bin" / "hermes")]
    for c in candidates:
        try:
            subprocess.run([c, "--version"], capture_output=True, timeout=5)
            return c
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def hermes_task(goal: str, timeout: int = 120) -> str:
    global _HERMES_BIN
    if _HERMES_BIN is None:
        _HERMES_BIN = _find_hermes()
    if _HERMES_BIN is None:
        return "Hermes Agent is not installed. Run: curl -fsSL https://hermes-agent.ai/install.sh | sh"

    try:
        result = subprocess.run(
            [_HERMES_BIN, "-z", goal],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        if result.returncode != 0:
            return f"Hermes error: {err[:200] or out[:200]}"
        if not out:
            return "Hermes completed the task."
        return out
    except subprocess.TimeoutExpired:
        return f"Hermes timed out after {timeout}s."
    except Exception as e:
        return f"Hermes failed: {e}"
