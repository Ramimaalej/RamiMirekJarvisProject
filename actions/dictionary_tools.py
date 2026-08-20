"""Dictionary tools — definitions, synonyms and examples via free API.

Intents: word_definition ("what does serendipity mean", "define ephemeral"),
         word_synonyms ("synonyms of happy"), word_example ("use ephemeral in a sentence")
"""
import json
import logging
import urllib.request

logger = logging.getLogger("dictionary")

_API = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"


def _fetch(word: str) -> list | None:
    """Fetch entries for a word; returns [] for 'no definition found',
    None for a real transport/network failure."""
    try:
        req = urllib.request.Request(
            _API.format(word=urllib.parse.quote(word.strip().lower())),
            headers={"User-Agent": "Jarvis/1.0", "Accept": "application/json"})
        body = urllib.request.urlopen(req, timeout=10).read()
        return json.loads(body)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        # dictionaryapi.dev sometimes serves 'No Definitions Found' as a 5xx
        # when its CDN misses; read the body and treat it as 'not found'.
        try:
            payload = json.loads(exc.read() or b"{}")
        except Exception:
            payload = {}
        if "no definitions" in (payload.get("title") or "").lower() or \
           "no definitions" in (payload.get("message") or "").lower() or \
           "couldn't find" in (payload.get("message") or "").lower():
            return []
        if exc.code >= 500:
            # Transient CDN failure (dictionaryapi returns 502 for
            # "not found" entries sometimes) — retry a few times.
            import time
            for attempt in range(3):
                time.sleep(0.5 + attempt)
                try:
                    body = urllib.request.urlopen(req, timeout=10).read()
                    data = json.loads(body)
                    if data:
                        return data
                    return []  # empty 200 → not found
                except urllib.error.HTTPError as inner:
                    try:
                        inner_payload = json.loads(inner.read() or b"{}")
                    except Exception:
                        inner_payload = {}
                    if "no definitions" in (inner_payload.get("title") or "").lower() or \
                       "couldn't find" in (inner_payload.get("message") or "").lower():
                        return []
                    continue
                except Exception:  # noqa: BLE001
                    continue
            logger.warning("dictionary retries exhausted %s: %s", exc.code, word)
            return None
        logger.warning("dictionary http error %s: %s", exc.code, word)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("dictionary error: %s", exc)
        return None


def word_definition(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    word = (parameters.get("word") or parameters.get("text") or "").strip()
    if not word:
        return "Tell me the word you want defined, for example: 'what does loquacious mean'."
    data = _fetch(word)
    if data is None:
        return "Could not reach the dictionary service. Check your internet connection."
    if not data:
        return f"No definition found for '{word}' in English."
    entry = data[0]
    meanings = entry.get("meanings", [])[:2]
    lines = []
    for m in meanings:
        part = m.get("partOfSpeech", "")
        for d in m.get("definitions", [])[:1]:
            defn = d.get("definition", "")
            ex = d.get("example", "")
            if defn:
                lines.append(f"{part + ': ' if part else ''}{defn}" +
                             (f" Example: {ex}" if ex else ""))
    return (f"'{entry.get('word', word)}' — " + " / ".join(lines)[:600]) if lines \
        else f"No definition found for '{word}' in English."


def word_synonyms(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    word = (parameters.get("word") or parameters.get("text") or "").strip()
    if not word:
        return "Tell me the word, for example: 'synonyms of happy'."
    data = _fetch(word)
    if data is None:
        return "Could not reach the dictionary service."
    if not data:
        return f"No synonyms found for '{word}'."
    syns: list[str] = []
    for m in data[0].get("meanings", [])[:2]:
        for rel in m.get("synonyms", [])[:4]:
            if rel:
                syns.append(rel)
    if not syns:
        return f"No synonyms listed for '{word}'."
    return f"Synonyms of '{word}': {', '.join(syns)[:500]}"


def word_example(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    word = (parameters.get("word") or parameters.get("text") or "").strip()
    if not word:
        return "Tell me the word, for example: 'use ephemeral in a sentence'."
    data = _fetch(word)
    if data is None:
        return "Could not reach the dictionary service."
    if not data:
        return f"No usage examples found for '{word}'."
    for m in data[0].get("meanings", []):
        for d in m.get("definitions", []):
            ex = d.get("example", "")
            if ex:
                return f"Example: \"{ex}\""
    return f"The dictionary has no example sentence for '{word}'."
