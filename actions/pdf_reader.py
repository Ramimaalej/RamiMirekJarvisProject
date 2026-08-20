"""Read any PDF from the user's files.

Usage (via Jarvis intent `read_pdf`):
    {"path": "/path/to/file.pdf"}

If no path is given, Jarvis looks in ~/Downloads and ~/Documents for PDFs.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("jarvis.pdf_reader")

# pdfplumber first (layout-preserving), fallback to pypdf
try:
    import pdfplumber  # noqa: F401
    _BACKEND = "pdfplumber"
except ImportError:
    try:
        import pypdf  # noqa: F401
        _BACKEND = "pypdf"
    except ImportError:
        _BACKEND = "none"


def _extract_text(path: Path, max_pages: int = 30) -> str:
    if _BACKEND == "pdfplumber":
        texts = []
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                if i >= max_pages:
                    break
                t = page.extract_text()
                if t:
                    texts.append(t)
        return "\n".join(texts)
    if _BACKEND == "pypdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        texts = []
        for i, page in enumerate(reader.pages):
            if i >= max_pages:
                break
            t = page.extract_text()
            if t:
                texts.append(t)
        return "\n".join(texts)
    return ""


def _recent_pdfs(limit: int = 5):
    candidates = [Path.home() / "Downloads", Path.home() / "Documents"]
    found = []
    for root in candidates:
        if not root.is_dir():
            continue
        for f in root.rglob("*.pdf"):
            found.append(f)
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found[:limit]


def read_pdf(parameters: dict, player=None) -> str:
    """Read a PDF and return its text summary.

    parameters: {"path": "...", "query": "..."}
    """
    path = (parameters.get("path") or "").strip()
    if not path:
        recent = _recent_pdfs()
        if not recent:
            return "I don't see any PDF in your Downloads or Documents. Give me the path, e.g. 'read this pdf C:/Users/rami/Downloads/cv.pdf'."
        first = recent[0]
        names = ", ".join(f.name for f in recent)
        return f"Here are your recent PDFs: {names}. Which one? Say 'read the pdf named <file>'."

    p = Path(path).expanduser()
    if not p.exists():
        return f"I cannot find that file: {path}"
    if p.suffix.lower() != ".pdf":
        return "This file is not a PDF. Say 'read this pdf <path>'."
    if p.stat().st_size > 100 * 1024 * 1024:
        return "This PDF is too large (>100MB) for me to read directly."

    text = _extract_text(p)
    if not text:
        return f"No text could be extracted from {p.name}. It may be a scanned PDF — say 'jarvis look at my screen' after opening it, and I can OCR it."

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    size = len(text)
    if size > 6000:
        text = text[:6000]
        cut = "... (truncated; ask me about specific parts)"
    else:
        cut = ""
    query = (parameters.get("query") or "").strip()
    header = f"Here is what is in {p.name}:" if not query else f"Contents of {p.name}:"
    out = f"{header}\n\n{text}\n{cut}".strip()
    logger.info("[pdf_reader] read %s (%d chars)", p.name, size)
    return out
