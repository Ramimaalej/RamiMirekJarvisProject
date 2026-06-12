import sys
import json
sys.path.insert(0, "/home/rami/Mark-XL-main")
from core.llm_client import _stream_openai, get_llm_settings, get_openai_endpoints

url, model = get_llm_settings()
endpoint, _ = get_openai_endpoints(url)
print(f"URL: {url}")
print(f"ENDPOINT: {endpoint}")
print(f"MODEL: {model}")

messages = [{"role": "user", "content": "hi"}]
try:
    for chunk in _stream_openai(messages, None, 10):
        print(chunk)
except Exception as e:
    print("ERROR:", e)
