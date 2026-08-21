import shutil
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def create_archive(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    source = (parameters.get("source") or "").strip()
    output = (parameters.get("output") or "archive.zip").strip()
    
    if not source:
        return "What folder or file should I archive?"
        
    try:
        base_name = output.rsplit('.', 1)[0]
        fmt = "zip" if output.endswith(".zip") else "tar"
        shutil.make_archive(base_name, fmt, source)
        return f"Archive created: {output}"
    except Exception as e:
        return f"Archiving failed: {e}"

def extract_archive(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    file = (parameters.get("file") or "").strip()
    dest = (parameters.get("dest") or "extracted").strip()
    
    if not file:
        return "What archive should I extract?"
        
    try:
        shutil.unpack_archive(file, dest)
        return f"Extracted to {dest}"
    except Exception as e:
        return f"Extraction failed: {e}"
