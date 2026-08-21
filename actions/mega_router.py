import re
import unicodedata

def normalize(text):
    text = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())

MEGA_INTENTS = [{'name': 'stock_market', 'patterns': ['stock.*price', 'prix.*action', 'market.*for', 'how.*is.*doing', 'action.*bourse', 'xauusd', 'gold.*price', 'prix.*or', 'forex', 'eurusd']}, {'name': 'translator', 'patterns': ['translate.*', 'traduis.*', 'comment.*dit.*on', 'traduction.*vers']}, {'name': 'media_downloader', 'patterns': ['download.*http', 'telecharger.*http', 'save.*http', 'youtube.*download']}, {'name': 'speedtest', 'patterns': ['speedtest', 'internet.*speed', 'vitesse.*internet', 'test.*debit', 'check.*speed']}, {'name': 'process_mgr', 'patterns': ['list.*processes', 'liste.*processus', 'qu.*est.*ce.*qui.*tourne', '(kill|stop|terminer|tuer).*(process|application|app)?', 'kill.*pid']}, {'name': 'archive_tools', 'patterns': ['(archive|zip|compress|compresser)', '(extract|unzip|decompresser|extraire)', 'create.*zip']}, {'name': 'image_edit', 'patterns': ['resize.*image', 'redimensionner.*image', '(grayscale|noir.*blanc)', '(flip|mirror)']}, {'name': 'wiki_tools', 'patterns': ['(wikipedia|wiki|search.*wiki)', '(who|what|qui|qu.*est.*ce.*que).*on.*wikipedia', 'wiki.*']}, {'name': 'system_health', 'patterns': ['check.*system.*health', 'sante.*systeme', 'etat.*pc', 'how.*is.*my.*pc', 'comment.*va.*mon.*ordinateur']}, {'name': 'news_pro', 'patterns': ['(get|show|read|affiche|donne|what.*the).*(news|actualites|latest)', '(tech|business|science|health|sports|entertainment).*news', 'news.*for', 'quoi.*de.*neuf', 'derniere.*info']}, {'name': 'devices_scan', 'patterns': ['what.*is.*connected', 'qu.*est.*ce.*qui.*est.*(branche|connecte)', 'connected.*devices', '(ecrans|monitors).*connectes']}, {'name': 'qr_tools', 'patterns': ['(generate|create|fais|genere).*qr.*code', '(scan|read|lire|scanner).*qr.*code']}, {'name': 'clipboard_mgr', 'patterns': ['what.*is.*in.*my.*clipboard', 'qu.*y.*a.*t.*il.*dans.*mon.*presse.*papiers', '(lis|read).*presse.*papiers', '(copy|copie).*clipboard']}, {'name': 'math_solver', 'patterns': ['(calcule|solve|combien.*fait)', '[0-9 ]+[+\\-*/^][0-9 ]+']}, {'name': 'hash_tools', 'patterns': ['(hash|md5|sha256)', 'md5.*of']}, {'name': 'random_tools', 'patterns': ['(roll|lance).*(d[0-9]+|dice|des)', '(pile.*face|heads.*tails)', '(choisis|pick|choisir).*entre']}, {'name': 'notes_tools', 'patterns': ['(note|memorise)', 'list.*my.*notes', 'liste.*mes.*notes', 'search.*notes']}, {'name': 'system_info_tools', 'patterns': ['(battery|batterie)', '(wifi|reseau)', '(disk|disque)']}, {'name': 'screen_ocr', 'patterns': ['(what.*on|see).*my.*screen', 'qu.*y.*a.*t.*il.*sur.*mon.*ecran', 'vois.*tu.*mon.*ecran', 'is.*word.*visible', 'mot.*visible.*sur.*l.*ecran', '(trouve|find).*mot.*sur.*mon.*ecran']}, {'name': 'check_crypto', 'patterns': ['(bitcoin|ethereum|crypto|btc|eth).*(price|value|cours|valeur|prix)', 'how.*much.*is.*(bitcoin|btc|eth)', '([a-z]+).*value']}, {'name': 'check_time', 'patterns': ['(what.*time|quelle.*heure)', '(time|heure).*in', 'heure.*a']}, {'name': 'create_document', 'patterns': ['(create|make|generate|write|build|cree|genere|fais).*(pdf|word|document|docx|report|fichier)']}, {'name': 'read_pdf', 'patterns': ['(read|lis|analyse).*pdf', 'qu.*y.*a.*t.*il.*dans.*pdf']}, {'name': 'install_tool', 'patterns': ['(install|installe)', 'setup']}, {'name': 'use_tool', 'patterns': ['(run|lance|utilise|use).*(nmap|ping|traceroute|netstat|dig|whois|curl|ssh|docker)']}, {'name': 'open_app', 'patterns': ['(open|lance|ouvre).*(terminal|console|shell|bash)']}, {'name': 'list_apps', 'patterns': ['(list|show|affiche|liste).*(apps|applications|software|logiciels)', 'what.*my.*installed.*apps']}, {'name': 'opencode_run', 'patterns': ['(execute|lance|demarre).*(new.*dev.*project|opencode)', '(build|cree).*with.*opencode']}, {'name': 'clone_and_run', 'patterns': ['(clone|cloner).*(github|repo|repository|depot)', 'clone.*http']}]

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
        
        if name == "open_app":
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
