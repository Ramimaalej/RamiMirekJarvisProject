import sys, json, requests
sys.path.insert(0, "/home/rami/Mark-XL-main")
from core.llm_client import get_llm_settings, get_openai_endpoints, get_llm_headers

url, model = get_llm_settings()
endpoint, _ = get_openai_endpoints(url)
headers = get_llm_headers()

messages = [
    {"role": "user", "content": "hello"},
    {"role": "assistant", "content": "", "tool_calls": [{"id": "call_123", "function": {"name": "save_memory", "arguments": "{}"}}]},
    {"role": "tool", "content": "Done", "tool_call_id": "call_123"},
    {"role": "user", "content": "open youtube"}
]

payload = {
    "model": model,
    "messages": messages,
    "max_tokens": 100
}

resp = requests.post(endpoint, json=payload, headers=headers)
print("Status:", resp.status_code)
print("Response:", resp.text)
