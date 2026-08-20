"""Voice language switching — 'Jarvis, speak French/Arabic/English...'.

Maps language names (FR/EN mixed) to ISO 639-1 codes and switches the
TTS engine voice at runtime, then confirms back in the chosen language.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("jarvis")

# Name aliases (FR + EN) -> ISO 639-1
_LANGUAGE_ALIASES: dict[str, str] = {
    # English names
    "arabic": "ar", "arab": "ar",
    "english": "en",
    "french": "fr",
    "spanish": "es", "espanol": "es", "español": "es",
    "german": "de", "deutsch": "de",
    "italian": "it", "italiano": "it",
    "portuguese": "pt", "portugues": "pt",
    "russian": "ru", "russe": "ru",
    "chinese": "zh", "mandarin": "zh",
    "japanese": "ja",
    "korean": "ko",
    "turkish": "tr", "turc": "tr",
    "hindi": "hi",
    "dutch": "nl",
    "polish": "pl", "polonais": "pl",
    "romanian": "ro", "roumain": "ro",
    "thai": "th", "thaï": "th", "thai": "th",
    "vietnamese": "vi", "vietnamien": "vi",
    "indonesian": "id", "indonesien": "id",
    "persian": "fa", "farsi": "fa",
    "urdu": "ur",
    "ukrainian": "uk", "ukrainien": "uk",
    "greek": "el", "grec": "el", "grece": "el",
    # French names
    "arabe": "ar",
    "anglais": "en",
    "francais": "fr", "français": "fr",
    "espagnol": "es",
    "allemand": "de",
}

# Confirmation messages in the target language
_CONFIRM = {
    "ar": "حسناً، سأتحدث بالعربية من الآن فصاعداً.",
    "en": "Alright, I will speak English from now on.",
    "fr": "D'accord, je parlerai français désormais.",
    "es": "De acuerdo, hablaré en español a partir de ahora.",
    "de": "Alles klar, ich spreche ab jetzt Deutsch.",
    "it": "D'accordo, parlerò in italiano d'ora in poi.",
    "pt": "Ok, vou falar português de agora em diante.",
    "ru": "Хорошо, теперь я говорю по-русски.",
    "zh": "好的，从现在起我会说中文。",
    "ja": "はい、これからは日本語で話します。",
    "ko": "알겠습니다, 이제부터 한국어로 말할게요.",
    "tr": "Tamam, bundan sonra Türkçe konuşacağım.",
    "hi": "ठीक है, अब मैं हिंदी बोलूँगा।",
    "nl": "Oké, ik spreek vanaf nu Nederlands.",
    "pl": "Dobrze, od teraz będę mówić po polsku.",
    "ro": "De acord, voi vorbi în română de acum înainte.",
    "th": "ตกลง ต่อไปผมจะพูดภาษาไทยครับ",
    "vi": "Được rồi, từ bây giờ tôi sẽ nói tiếng Việt.",
    "id": "Baik, mulai sekarang saya akan berbicara bahasa Indonesia.",
    "fa": "باشه، از این به بعد فارسی صحبت می‌کنم.",
    "ur": "ٹھیک ہے، اب سے میں اردو میں بات کروں گا۔",
    "uk": "Гаразд, тепер я говоритиму українською.",
    "el": "Εντάξει, από εδώ και πέρα θα μιλάω ελληνικά.",
}


def _resolve_lang(text: str) -> str | None:
    """Resolve an ISO code from a phrase like 'speak french' / 'parle arabe'."""
    low = text.lower()
    for alias, code in _LANGUAGE_ALIASES.items():
        if f" {alias} " in f" {low} " or low.endswith(f" {alias}") or low.startswith(f"{alias} "):
            return code
    return None


def set_tts_language(parameters: dict, player=None) -> str:
    """Switch the TTS voice to a language.

    parameters: {"language": "french"|"arabe"|... | "fr"}
    """
    text = (parameters.get("language") or parameters.get("lang") or "").strip()
    if not text:
        return "Which language? Say 'speak French' or 'parle arabe'."
    code = _resolve_lang(text) or (text[:2] if len(text) == 2 else None)
    if not code:
        return f"I don't know the language '{text}'."

    switched = False
    # The player lives on the JarvisLocal instance passed via `player`
    # (core/jarvis_llm forwards the assistant wrapper).  Fall back to
    # rebuilding the config file so the next start keeps the choice.
    if player is not None and hasattr(player, "_tts"):
        tts = getattr(player, "_tts")
        if tts is not None and hasattr(tts, "set_language"):
            switched = tts.set_language(code)
        elif tts is not None and hasattr(tts, "set_language"):
            switched = tts.set_language(code)
    elif player is not None:
        # `player` may be the UI — locate the assistant via its speak attr
        for attr in ("_tts",):
            if hasattr(player, attr):
                tts = getattr(player, attr)
                if tts is not None and hasattr(tts, "set_language"):
                    switched = tts.set_language(code)
                    break

    if not switched:
        # Persist the choice so it applies from the next session.
        cfg_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
        try:
            import json
            cfg = {}
            if cfg_path.exists():
                with open(cfg_path, encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg["tts_language"] = code
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            switched = True
        except Exception as e:
            logger.error("set_language: persist failed — %s", e)

    if not switched:
        return f"Sorry, I cannot switch to that language yet."

    reply = _CONFIRM.get(code, f"Alright, I will now speak that language.")
    logger.info("[set_language] Switched to '%s'", code)
    return reply
