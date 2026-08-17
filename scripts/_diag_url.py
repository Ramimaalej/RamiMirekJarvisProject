import sys
sys.path.insert(0, ".")
import json, os
from pathlib import Path
from unittest import mock

os.chdir("/home/ubuntu/RamiMirekJarvisProject")
# Simulate a config where groq is provider but llm_url is leftover localhost
cfg = {"llm_provider": "groq", "llm_model": "llama-3.3-70b-versatile",
       "llm_url": "http://localhost:11434", "groq_api_key": "gsk_test"}
cfg_path = Path("config/api_keys.json")
bak = cfg_path.read_text(encoding="utf-8") if cfg_path.exists() else None
cfg_path.parent.mkdir(exist_ok=True)
cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

from core.llm_client import get_llm_settings, get_llm_provider
url, model = get_llm_settings()
print("provider:", get_llm_provider())
print("url:", url, "model:", model)

if bak is not None:
    cfg_path.write_text(bak, encoding="utf-8")
else:
    cfg_path.unlink(missing_ok=True)
