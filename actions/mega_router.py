import re
import unicodedata


def normalize(text):
    text = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())

MEGA_INTENTS = [
    {"name": "youtube_video", "patterns": [
        r"\b(?:open|play|search|find)\b.*\b(?:youtube|yt)\b",
        r"\b(?:youtube|yt)\b.*\b(?:playlist|music|song|video)\b",
    ]},
    {"name": "stock_market", "patterns": [
        r"stock.*price", r"prix.*action", r"market.*for", r"how.*is.*doing",
        r"action.*bourse", r"xauusd", r"gold.*price", r"prix.*or", r"forex", r"eurusd",
    ]},
    {"name": "translator", "patterns": [r"translate.*", r"traduis.*", r"comment.*dit.*on", r"traduction.*vers"]},
    {"name": "media_downloader", "patterns": [r"download.*http", r"telecharger.*http", r"save.*http", r"youtube.*download"]},
    {"name": "speedtest", "patterns": [r"speedtest", r"internet.*speed", r"vitesse.*internet", r"test.*debit", r"check.*speed"]},
    {"name": "process_mgr", "patterns": [r"list.*processes", r"liste.*processus", r"qu.*est.*ce.*qui.*tourne", r"(kill|stop|terminer|tuer).*(process|application|app)?", r"kill.*pid"]},
    {"name": "archive_tools", "patterns": [r"(archive|zip|compress|compresser)", r"(extract|unzip|decompresser|extraire)", r"create.*zip"]},
    {"name": "image_edit", "patterns": [r"resize.*image", r"redimensionner.*image", r"(grayscale|noir.*blanc)", r"(flip|mirror)"]},
    {"name": "wiki_tools", "patterns": [r"(wikipedia|wiki|search.*wiki)", r"(who|what|qui|qu.*est.*ce.*que).*on.*wikipedia", r"wiki.*"]},
    {"name": "system_health", "patterns": [r"check.*system.*health", r"sante.*systeme", r"etat.*pc", r"how.*is.*my.*pc", r"comment.*va.*mon.*ordinateur"]},
    {"name": "news_pro", "patterns": [r"(get|show|read|affiche|donne|what.*the).*(news|actualites|latest)", r"(tech|business|science|health|sports|entertainment).*news", r"news.*for", r"quoi.*de.*neuf", r"derniere.*info"]},
    {"name": "devices_scan", "patterns": [r"what.*is.*connected", r"qu.*est.*ce.*qui.*est.*(branche|connecte)", r"connected.*devices", r"(ecrans|monitors).*connectes"]},
    {"name": "qr_tools", "patterns": [r"(generate|create|fais|genere).*qr.*code", r"(scan|read|lire|scanner).*qr.*code"]},
    {"name": "clipboard_mgr", "patterns": [r"what.*is.*in.*my.*clipboard", r"qu.*y.*a.*t.*il.*dans.*mon.*presse.*papiers", r"(lis|read).*presse.*papiers", r"(copy|copie).*clipboard"]},
    {"name": "math_solver", "patterns": [r"(calcule|solve|combien.*fait)", r"[0-9 ]+[+\-*/^][0-9 ]+"]},
    {"name": "hash_tools", "patterns": [r"(hash|md5|sha256)", r"md5.*of"]},
    {"name": "random_tools", "patterns": [r"(roll|lance).*(d[0-9]+|dice|des)", r"(pile.*face|heads.*tails)", r"(choisis|pick|choisir).*entre"]},
    {"name": "notes_tools", "patterns": [r"(note|memorise)", r"list.*my.*notes", r"liste.*mes.*notes", r"search.*notes"]},
    {"name": "system_info_tools", "patterns": [r"(battery|batterie)", r"(wifi|reseau)", r"(disk|disque)"]},
    {"name": "screen_ocr", "patterns": [r"(what.*on|see).*my.*screen", r"qu.*y.*a.*t.*il.*sur.*mon.*ecran", r"vois.*tu.*mon.*ecran", r"is.*word.*visible", r"mot.*visible.*sur.*l.*ecran", r"(trouve|find).*mot.*sur.*mon.*ecran"]},
    {"name": "check_crypto", "patterns": [r"(bitcoin|ethereum|crypto|btc|eth).*(price|value|cours|valeur|prix)", r"how.*much.*is.*(bitcoin|btc|eth)", r"([a-z]+).*value"]},
    {"name": "check_time", "patterns": [r"(what.*time|quelle.*heure)", r"(time|heure).*in", r"heure.*a"]},
    {"name": "create_document", "patterns": [r"(create|make|generate|write|build|cree|genere|fais).*(pdf|word|document|docx|report|fichier)"]},
    {"name": "read_pdf", "patterns": [r"(read|lis|analyse).*pdf", r"qu.*y.*a.*t.*il.*dans.*pdf"]},
    {"name": "install_tool", "patterns": [r"(install|installe)", r"setup"]},
    {"name": "use_tool", "patterns": [r"(run|lance|utilise|use).*(nmap|ping|traceroute|netstat|dig|whois|curl|ssh|docker)"]},
    {"name": "open_app", "patterns": [r"(open|lance|ouvre).*(terminal|console|shell|bash)"]},
    {"name": "list_apps", "patterns": [r"(list|show|affiche|liste).*(apps|applications|software|logiciels)", r"what.*my.*installed.*apps"]},
    {"name": "opencode_run", "patterns": [r"(execute|lance|demarre).*(new.*dev.*project|opencode)", r"(build|cree).*with.*opencode"]},
    {"name": "clone_and_run", "patterns": [r"(clone|cloner).*(github|repo|repository|depot)", r"clone.*http"]},
]

_MARKET_SYMBOLS = ("XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "BTCUSD", "ETHUSD")


def _market_symbol(text: str) -> str:
    symbol_match = re.search(r"\b(" + "|".join(_MARKET_SYMBOLS) + r")\b", text, re.IGNORECASE)
    if symbol_match:
        return symbol_match.group(1).upper()
    if "gold" in text or "or" in text.split():
        return "GOLD"
    if "silver" in text or "argent" in text.split():
        return "SILVER"
    return ""


def _youtube_query(text: str) -> str:
    query = re.sub(r"^(?:open|play|search|find)\s+(?:a|an|the)?\s*", "", text, flags=re.IGNORECASE)
    query = re.sub(r"\s+(?:on|in|from|at)\s+(?:youtube|yt)\s*$", "", query, flags=re.IGNORECASE)
    return query.strip() or "YouTube"

def mega_route(text):
    norm_text = normalize(text)
    if not norm_text: return None
    best_match = None
    best_score = 0
    
    for intent in MEGA_INTENTS:
        for p in intent["patterns"]:
            m = re.search(p, norm_text, re.IGNORECASE)
            if m:
                # Priorité aux matches plus longs
                score = len(m.group(0)) / len(norm_text)
                if score > best_score:
                    best_score = score
                    best_match = (intent["name"], m)
    
    if best_match and best_score > 0.1:
        name, m = best_match
        params = {}
        
        # Extraction intelligente
        full_match = m.group(0)
        remaining = norm_text[m.end():].strip()
        
        if name == "stock_market":
            symbol = _market_symbol(norm_text)
            if symbol:
                params["symbol"] = symbol
        elif name == "youtube_video":
            params["action"] = "open_search"
            params["query"] = _youtube_query(norm_text)
        elif name == "open_app":
            # For "open terminal", m.group(0) is "open terminal"
            # We need to extract "terminal"
            import re as _re
            app_match = _re.search(r'(?:open|lance|ouvre)\s+(.+)', full_match, _re.IGNORECASE)
            if app_match:
                params["app_name"] = app_match.group(1).strip()
            elif remaining:
                params["app_name"] = remaining
        elif remaining:
            params["query"] = remaining
            
        return {"intent": name, "params": params, "confidence": best_score}
    return None
