import requests
import logging

logger = logging.getLogger(__name__)

def translate_text(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    text = (parameters.get("text") or "").strip()
    target = (parameters.get("target_lang") or "fr").strip().lower()
    
    if not text:
        return "What text should I translate?"
    
    # Simple map for common names to ISO codes
    lang_map = {"french": "fr", "français": "fr", "english": "en", "anglais": "en", "arabic": "ar", "arabe": "ar", "spanish": "es", "espagnol": "es", "german": "de", "allemand": "de"}
    target = lang_map.get(target, target)
    
    try:
        # Using MyMemory Free API
        url = f"https://api.mymemory.translated.net/get?q={text}&langpair=auto|{target}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        translated = data["responseData"]["translatedText"]
        return f"Translation ({target}): {translated}"
    except Exception as e:
        logger.error("Translation error: %s", e)
        return f"Translation failed: {str(e)}"
