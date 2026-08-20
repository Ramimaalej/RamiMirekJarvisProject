"""Hash tools — MD5 and SHA-256 of text or files.

Intents: hash_string ("hash this text: hello"), hash_file ("sha256 of myfile.txt")
"""
import hashlib
import logging
from pathlib import Path

logger = logging.getLogger("hash_tools")


def _hash(data: bytes, algo: str) -> str:
    h = hashlib.new(algo)
    h.update(data)
    return h.hexdigest()


def hash_string(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    text = parameters.get("text") or parameters.get("content") or ""
    algo = (parameters.get("algo") or "sha256").lower()
    if algo not in ("md5", "sha256"):
        algo = "sha256"
    if not text:
        return "Tell me the text to hash, for example: 'hash the text hello world'."
    md = _hash(text.encode("utf-8"), algo)
    return f"{algo.upper()} of your text: {md}"


def hash_file(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    path = (parameters.get("path") or parameters.get("file") or "").strip()
    algo = (parameters.get("algo") or "sha256").lower()
    if algo not in ("md5", "sha256"):
        algo = "sha256"
    if not path:
        return "Tell me the file to hash, for example: 'hash the file report.pdf'."
    p = Path(path).expanduser()
    if not p.exists():
        return f"I cannot find the file {p}."
    try:
        md = _hash(p.read_bytes(), algo)
        return f"{algo.upper()} of {p.name}: {md}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("hash_file error: %s", exc)
        return f"Could not hash {p.name}: {exc}"
