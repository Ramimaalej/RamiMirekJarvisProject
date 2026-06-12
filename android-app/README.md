# MARK XL — Android Mobile Interface

Turn your phone into a mobile Jarvis terminal connected to your local PC AI assistant.

## Architecture

```
Phone (this app) ──WebSocket──> PC Bridge (pc_bridge.py) ──> Jarvis AI (main.py)
       │                                                         │
   Voice input                                              18+ tools
   Text input                                                LLM (Ollama)
   Speech output                                             Memory, Skills
```

## 1. Run the PC Bridge

On your PC, alongside your existing MARK XL setup:

```bash
cd /path/to/Mark-XL
python pc_bridge.py
```

The bridge will:
- Print your PC's local IP addresses
- Display a QR code — scan with your phone
- Listen on port 8765 for WebSocket connections

**You must have `websockets` and `qrcode` installed** (auto-installed on first run).

## 2. Connect the Phone App

1. Open the MARK XL app on your phone
2. Go to **Settings** (gear icon)
3. Enter your PC's IP address (shown on pc_bridge.py output)
4. Keep the default port **8765**
5. Tap **CONNECT**
6. Green dot = connected

Or scan the QR code shown in the terminal.

## 3. Build the APK

### Prerequisites
- Node.js 18+
- Java 17+ (JDK)
- Android Studio with SDK (API 34)
- `ANDROID_HOME` environment variable set

### Build commands

```bash
cd android-app
npm install
npx expo run:android
```

This compiles a debug APK. The APK will be at:
```
android/app/build/outputs/apk/debug/app-debug.apk
```

To build a release APK:

```bash
npx expo run:android --variant release
```

### Sideload the APK

1. Copy `app-debug.apk` to your phone
2. Open it with any file manager
3. Allow installation from unknown sources when prompted

## 4. Set as Default Assist App (Google Assistant replacement)

1. Go to **Settings > Apps > Default Apps > Digital Assistant App**
2. Tap **Default digital assistant app**
3. Select **MARK XL**

Now when you hold the home button, MARK XL launches instead of Google Assistant.

## Features

- **Voice input** — Tap/Hold the talk button, speak your command, release to send
- **Text input** — Type commands at the bottom
- **Chat history** — Full conversation log with timestamps
- **Arc Reactor** — Animated visual states: idle, listening, thinking, speaking
- **Settings** — Configure PC IP, port, wake word, voice speed
- **Auto-connect** — Reconnects every 5 seconds if disconnected
- **Dark theme** — Deep navy/black with electric blue accents

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Connection refused" | Make sure `pc_bridge.py` is running |
| Can't connect | Both devices must be on the same WiFi network |
| No response from Jarvis | Check that Ollama is running on the PC |
| Microphone not working | Grant the app microphone permission in Settings |
