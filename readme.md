# MARK XL — J.A.R.V.I.S AI Assistant

> **J**ust **A** **R**ather **V**ery **I**ntelligent **S**ystem  
> Cross-platform voice AI assistant with offline speech recognition, local/cloud LLM, browser automation, memory, and OS-level control.

---

## Table of Contents

- [What Is This?](#what-is-this)
- [System Requirements](#system-requirements)
- [Installation (A–Z)](#installation-a-z)
  - [1. Install Python](#1-install-python)
  - [2. Install System Dependencies](#2-install-system-dependencies)
  - [3. Clone / Download the Project](#3-clone--download-the-project)
  - [4. Create a Virtual Environment](#4-create-a-virtual-environment)
  - [5. Install Python Packages](#5-install-python-packages)
  - [6. Install Playwright Browser](#6-install-playwright-browser)
  - [7. Install & Configure Ollama (for local LLM)](#7-install--configure-ollama-for-local-llm)
  - [8. Configure API Keys](#8-configure-api-keys)
  - [9. Run MARK XL](#9-run-mark-xl)
- [First-Time Startup](#first-time-startup)
- [Configuration Reference](#configuration-reference)
- [Usage](#usage)
  - [Voice Commands](#voice-commands)
  - [Keyboard Shortcuts](#keyboard-shortcuts)
  - [Configuration Panel](#configuration-panel)
- [All Tools & Capabilities](#all-tools--capabilities)
- [TTS Engine Comparison](#tts-engine-comparison)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)

---

## What Is This?

MARK XL is a real-time voice AI assistant that runs **on your own computer**. It:

- Listens to your voice (offline, using Whisper or Vosk)
- Understands and responds using an LLM (local via Ollama, or cloud via NVIDIA NIM / OpenAI / Groq / etc.)
- Speaks back (EdgeTTS cloud, Kokoro offline, or ElevenLabs)
- Controls your computer: open apps, click buttons, fill forms, browse the web, manage files, send messages, and more
- Remembers personal facts (long-term memory)
- Runs background agents and scheduled tasks
- Has a PyQt6 desktop HUD with live system monitor

---

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **OS** | Linux (Fedora/Ubuntu/Arch), macOS, Windows | Linux |
| **Python** | 3.11 | 3.14 |
| **RAM** | 4 GB | 16 GB |
| **Disk** | 2 GB free | 10 GB (for LLM models) |
| **Microphone** | Any | Any |
| **Speakers** | Any | Any |
| **Internet** | Required for EdgeTTS / cloud LLMs | Optional for offline mode (Kokoro + Ollama) |
| **GPU** | Not required | NVIDIA GPU for faster Whisper / local LLM |

---

## Installation (A–Z)

### 1. Install Python

<details>
<summary><b>Fedora</b></summary>

```bash
sudo dnf install python3 python3-pip python3-devel python3-venv
```
</details>

<details>
<summary><b>Ubuntu / Debian</b></summary>

```bash
sudo apt update && sudo apt install python3 python3-pip python3-dev python3-venv
```
</details>

<details>
<summary><b>macOS</b></summary>

```bash
brew install python@3.14
```
</details>

<details>
<summary><b>Windows</b></summary>

Download from [python.org](https://www.python.org/downloads/) — check **"Add Python to PATH"** during install.
</details>

Verify:
```bash
python3 --version   # Should show Python 3.11+
```

### 2. Install System Dependencies

<details>
<summary><b>Fedora</b></summary>

```bash
sudo dnf install portaudio-devel libsndfile-devel cmake gcc-c++
# Accessibility (screen reader) — optional:
sudo dnf install python3-pyatspi
```
</details>

<details>
<summary><b>Ubuntu / Debian</b></summary>

```bash
sudo apt install portaudio19-dev libsndfile1-dev cmake build-essential
# Accessibility — optional:
sudo apt install python3-pyatspi
```
</details>

<details>
<summary><b>macOS</b></summary>

```bash
brew install portaudio libsndfile cmake
```
</details>

<details>
<summary><b>Windows</b></summary>

No extra system deps needed — everything comes with pip.
</details>

### 3. Clone / Download the Project

```bash
git clone <repository-url> Mark-XL
cd Mark-XL
```

### 4. Create a Virtual Environment

```bash
python3 -m venv .venv
```

Activate it:

| OS | Command |
|----|---------|
| Linux / macOS | `source .venv/bin/activate` |
| Windows (cmd) | `.venv\Scripts\activate.bat` |
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |

You should see `(.venv)` in your terminal prompt.

### 5. Install Python Packages

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Install STT and TTS packages (choose one per category):

```bash
# STT — Whisper (default, recommended):
pip install faster-whisper
# OR Vosk (alternative):
# pip install vosk

# TTS — EdgeTTS (default, free, needs internet):
pip install edge-tts
# OR Kokoro (fully offline, higher quality):
# pip install kokoro
# OR ElevenLabs (cloud API, paid):
# pip install elevenlabs
```

### 6. Install Playwright Browser

Required for browser automation tools.

```bash
playwright install chromium
```

On Fedora, you may also need:
```bash
sudo dnf install libnss3 libnspr4 libatk-1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
  libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
  libpango-1.0-0 libcairo2 libasound2
```

### 7. Install & Configure Ollama (for local LLM)

Skip this step if you plan to use a cloud provider (NVIDIA NIM, OpenAI, Groq, etc.).

```bash
# Install Ollama:
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model (start with a small one for testing):
ollama pull qwen2.5:0.5b

# For better results (needs ~8 GB RAM):
ollama pull qwen2.5:7b
```

Ollama runs as a background service on port `11434`.

### 8. Configure API Keys

Edit `config/api_keys.json`:

```json
{
  "stt_engine": "whisper",
  "stt_model": "tiny",
  "stt_language": "en",
  "llm_provider": "ollama",
  "llm_url": "http://localhost:11434",
  "llm_model": "qwen2.5:7b",
  "tts_engine": "edgetts",
  "tts_voice": "en-US-GuyNeural"
}
```

**For cloud LLM providers**, add your API key:

| Provider | `llm_provider` | Key field |
|----------|----------------|-----------|
| Ollama (local) | `ollama` | — |
| NVIDIA NIM | `nvidia_nim` | `nvidia_api_key` |
| OpenAI | `openai` | `openai_api_key` |
| Groq | `groq` | `groq_api_key` |
| OpenRouter | `openrouter` | `openrouter_api_key` |
| Gemini | `gemini` | `gemini_api_key` |
| Anthropic | `anthropic` | `anthropic_api_key` |

### 9. Run MARK XL

```bash
source .venv/bin/activate
python main.py
```

---

## First-Time Startup

On first run, MARK XL:

1. **Auto-installs** base packages (PyQt6, numpy, etc.) and restarts once
2. Opens the **startup panel** — shows LLM, STT, and TTS loading in parallel
3. Comes online in ~3-10 seconds (TTS may load in background)
4. Starts **listening** — you'll see the HUD and a pulsing microphone indicator

If something fails, check the log panel (right side of the window) for error messages.

---

## Configuration Reference

| Key | Values | Default | Description |
|-----|--------|---------|-------------|
| `stt_engine` | `whisper`, `vosk` | `whisper` | Speech-to-text engine |
| `stt_model` | `tiny`, `base`, `small`, `medium`, `large-v3` | `tiny` | Whisper model size (larger = slower but more accurate) |
| `stt_language` | `auto` or ISO code (`en`, `fr`, `de`, `tr`...) | `en` | STT language |
| `llm_provider` | `ollama`, `nvidia_nim`, `openai`, `groq`, `openrouter`, `gemini`, `anthropic`, `lmstudio` | `ollama` | LLM backend |
| `llm_url` | URL | `http://localhost:11434` | LLM API endpoint |
| `llm_model` | Model name | `qwen2.5:0.5b` | Model to use |
| `llm_api_key` | Key | `""` | API key for cloud LLMs |
| `tts_engine` | `edgetts`, `kokoro`, `elevenlabs` | `edgetts` | Text-to-speech engine |
| `tts_voice` | Voice name | `en-US-GuyNeural` | TTS voice |
| `tts_speed` | `0.5` – `2.0` | `1.0` | Speech speed multiplier |
| `theme` | `dark`, `light` | `dark` | UI theme |

All settings can be changed at runtime via the **⚙ Configure** button — no restart needed.

### Optional API Keys (set as needed)

| Key | Service |
|-----|---------|
| `nvidia_api_key` | NVIDIA NIM cloud LLM |
| `openai_api_key` | OpenAI / Azure OpenAI |
| `groq_api_key` | Groq cloud LLM |
| `gemini_api_key` | Google Gemini |
| `anthropic_api_key` | Anthropic Claude |
| `elevenlabs_api_key` | ElevenLabs TTS |
| `github_access_token` | GitHub integration |
| `plaid_client_id` / `plaid_secret` | Plaid finance |
| `fantastic_jobs_api_key` | Job search |
| `gws_credentials` | Google Workspace (Gmail, Calendar, Drive) |
| `spotify_client_id` / `spotify_client_secret` | Spotify (stub) |
| `livekit_api_key` / `livekit_api_secret` | LiveKit voice calls |

---

## Usage

### Voice Commands

Just speak naturally. JARVIS handles:

| Category | Examples |
|----------|----------|
| **General chat** | "Hello", "How are you?", "Tell me a joke" |
| **Questions** | "What is the capital of France?", "Who won the Nobel Prize in Physics in 2024?" |
| **Web search** | "What is the bitcoin price?", "Latest AI news", "Weather in London" |
| **Open apps** | "Open Chrome", "Open WhatsApp", "Open calculator" |
| **Browser** | "Go to YouTube", "Search python tutorials on YouTube", "Open Gmail and read my emails" |
| **Files** | "Create a file called notes.txt on the desktop", "Find my resume", "Show disk usage" |
| **Computer** | "Set volume to 50%", "Take a screenshot", "Lock my computer" |
| **Email** | "Send an email to John saying I'll be late", "Read my latest emails" |
| **Reminders** | "Remind me to call mom in 30 minutes", "Set a timer for 12 minutes" |
| **Memory** | "Remember that my favorite color is blue", "What do you know about me?" |
| **YouTube** | "Play lofi music on YouTube", "Summarize this video" |
| **System** | "Check disk space", "Run command: df -h", "What processes are using the most CPU?" |
| **Agents** | "Monitor the downloads folder for new PDFs", "Research quantum computing and save to a file" |
| **Tools** | "Calculate 15% of 340", "Take a picture", "Detect faces" |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `F4` | Mute / unmute microphone |
| `F11` | Toggle fullscreen |

### Configuration Panel

Click the **⚙ Configure** button (right panel) to change any setting at runtime:

- Switch LLM provider (Ollama ↔ NVIDIA NIM ↔ OpenAI ↔ Groq)
- Change STT model or language
- Switch TTS voice or engine
- All changes apply immediately — no restart needed

---

## All Tools & Capabilities

| Category | Tools |
|----------|-------|
| **System** | `open_app`, `computer_settings`, `computer_control`, `desktop_control`, `monitors`, `remote_control`, `package_manager`, `network_scan`, `run_command`, `run_python` |
| **Files** | `file_controller`, `file_processor`, `file_search`, `file_search_fast` |
| **Browser** | `browser_control` (Playwright: go_to, search, click, type, screenshot, fill forms), `browser_use` (AI browser agent) |
| **Web** | `web_search`, `youtube_video` |
| **Communication** | `send_message` (WhatsApp/Telegram), voice calls (LiveKit), Gmail (read, send, reply, search) |
| **Calendar** | Google Calendar (agenda, create events, delete events), Google Meet |
| **Productivity** | `reminder`, `timer`, `tasks`, `goal_engine`, `task_graph`, `budget_tracker`, `scaffold` |
| **Knowledge** | `save_memory`, `search_memory` (semantic/vector), `vault` (encrypted secrets), `context_bus` |
| **Data & Finance** | `stock_price`, `finance` (Plaid), `budget`, `weather_report`, `flight_finder`, `news`, `maps` |
| **Media** | `youtube_video`, `generate_image`, `screen_process` (vision), `screen_explain` (local), `screen_read` (accessibility) |
| **Development** | `code_helper`, `dev_agent`, `github`, `scaffold` |
| **AI & Agents** | `agent_task`, `manage_agents`, `manage_scheduler`, `manage_skills`, `calculate` |
| **Forensics** | `forensics` (file/process/network history) |
| **Other** | `get_location`, `get_datetime`, `detect_faces`, `wake_word`, `books`, `jobs`, `game_updater` |

---

## TTS Engine Comparison

| Engine | Internet | Quality | Speed | Cost | Notes |
|--------|----------|---------|-------|------|-------|
| **EdgeTTS** | Required | Good | Fast | Free | Default. Uses Microsoft Edge online API |
| **Kokoro** | No | Excellent | Medium | Free | Fully offline. ~100 MB model, loads ~20s first time |
| **ElevenLabs** | Required | Best | Fast | Paid | Cloud API. Most natural voice |

---

## Troubleshooting

### `ModuleNotFoundError: No module named '...'`

```bash
source .venv/bin/activate
pip install <missing-module>
```

### `externally-managed-environment` Error

You're using a system Python managed by your OS package manager. Always use a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### "Ollama is not running"

```bash
# Start Ollama:
ollama serve

# Or install as systemd service:
sudo systemctl enable --now ollama
```

### "No module named 'playwright'" when using browser

```bash
source .venv/bin/activate
pip install playwright
playwright install chromium
```

### "No module named 'pyatspi'"

Accessibility features (screen reader) need the system package:

```bash
sudo dnf install python3-pyatspi     # Fedora
sudo apt install python3-pyatspi     # Ubuntu/Debian
```

### Playwright fails on Fedora

```bash
sudo dnf install libnss3 libnspr4 libatk-1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
  libgbm1 libpango-1.0-0 libcairo2 libasound2
```

### Microphone not working

```bash
# List audio devices:
python -c "import sounddevice as sd; print(sd.query_devices())"
# Test recording:
python -c "
import sounddevice as sd
import numpy as np
rec = sd.rec(int(3*16000), samplerate=16000, channels=1)
sd.wait()
print('Recorded', len(rec), 'samples')
"
```

### JARVIS doesn't respond or responds slowly

1. **Check the LLM** — If using Ollama, make sure the model is pulled and Ollama is running
2. **Check logs** — Look at the right panel in the UI for error messages
3. **Try a smaller model** — `qwen2.5:0.5b` is fastest for testing
4. **Cloud provider too slow?** — The 550B NVIDIA NIM model is inherently slow; try a smaller cloud model or switch to Ollama locally

### Can't hear JARVIS

- Check your system audio output
- Try a different TTS engine (`edgetts` → `kokoro`)
- Adjust `tts_voice` in config
- Check if muted (F4 toggles mute)

---

## Project Structure

```
Mark-XL/
├── main.py                 # Main application (entry point)
├── ui.py                   # PyQt6 desktop HUD
├── requirements.txt        # Python dependencies
├── config/
│   └── api_keys.json       # All configuration and API keys
├── core/
│   ├── llm_client.py       # LLM API client (Ollama, OpenAI, NVIDIA, etc.)
│   ├── stt.py              # Speech-to-text (Whisper, Vosk)
│   ├── tts.py              # Text-to-speech (EdgeTTS, Kokoro, ElevenLabs)
│   ├── prompt.txt          # JARVIS system prompt
│   └── scheduler.py        # Background task scheduler
├── actions/                # All tool implementations
│   ├── open_app.py         # Launch applications
│   ├── browser_control.py  # Playwright browser automation
│   ├── web_search.py       # Web search
│   ├── file_controller.py  # File operations
│   ├── computer_control.py # Mouse/keyboard/shell
│   ├── send_message.py     # WhatsApp/Telegram
│   └── ... (50+ tools)
├── memory/
│   ├── memory_manager.py   # Long-term memory (JSON)
│   └── vector_memory.py    # Semantic search memory
├── agent/
│   ├── agent_manager.py    # Background agent lifecycle
│   ├── executor.py         # Multi-step task executor
│   └── planner.py          # LLM-based task planning
├── skills/
│   └── definitions/        # Domain skill definitions (auto-trigger)
├── tests/                  # Test suite
│   ├── test_all.py
│   └── test_features.py
├── gws_bridge.py           # Google Workspace integration
├── pc_bridge.py            # Phone companion bridge
└── android-app/            # Android companion app (Expo/React Native)
```

---

## License

MIT — FatihMakes Industries
