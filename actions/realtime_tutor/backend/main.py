from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import asyncio
import json
import os
import sys
from pathlib import Path
from websockets import connect
from typing import Dict

_PARENT = Path(__file__).resolve().parent
_CONFIG_PATH = _PARENT.parent.parent.parent / "config" / "api_keys.json"
_GEMINI_KEY = ""
try:
    _cfg = json.loads(_CONFIG_PATH.read_text())
    _GEMINI_KEY = (_cfg.get("gemini_api_key") or "").strip()
except Exception:
    pass

_FRONTEND_DIR = _PARENT.parent / "frontend" / "out"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def serve_index():
    return FileResponse(_FRONTEND_DIR / "index.html")


@app.get("/{path:path}")
async def serve_static(path: str):
    fp = _FRONTEND_DIR / path
    if fp.exists() and fp.is_file():
        return FileResponse(fp)
    return FileResponse(_FRONTEND_DIR / "index.html")


class GeminiConnection:
    def __init__(self):
        self.api_key = _GEMINI_KEY
        self.model = "gemini-2.0-flash-exp"
        self.uri = (
            "wss://generativelanguage.googleapis.com/ws/"
            "google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent"
            f"?key={self.api_key}"
        )
        self.ws = None
        self.config = None

    async def connect(self):
        self.ws = await connect(self.uri, additional_headers={"Content-Type": "application/json"})

        if not self.config:
            raise ValueError("Configuration must be set before connecting")

        setup_message = {
            "setup": {
                "model": f"models/{self.model}",
                "generation_config": {
                    "response_modalities": ["AUDIO"],
                    "speech_config": {
                        "voice_config": {
                            "prebuilt_voice_config": {
                                "voice_name": self.config["voice"]
                            }
                        }
                    }
                },
                "system_instruction": {
                    "parts": [
                        {
                            "text": self.config["systemPrompt"]
                        }
                    ]
                }
            }
        }
        await self.ws.send(json.dumps(setup_message))
        setup_response = await self.ws.recv()
        return setup_response

    def set_config(self, config):
        self.config = config

    async def send_audio(self, audio_data: str):
        realtime_input_msg = {
            "realtime_input": {
                "media_chunks": [
                    {
                        "data": audio_data,
                        "mime_type": "audio/pcm"
                    }
                ]
            }
        }
        await self.ws.send(json.dumps(realtime_input_msg))

    async def receive(self):
        return await self.ws.recv()

    async def close(self):
        if self.ws:
            await self.ws.close()

    async def send_image(self, image_data: str):
        image_message = {
            "realtime_input": {
                "media_chunks": [
                    {
                        "data": image_data,
                        "mime_type": "image/jpeg"
                    }
                ]
            }
        }
        await self.ws.send(json.dumps(image_message))

    async def send_text(self, text: str):
        text_message = {
            "client_content": {
                "turns": [
                    {
                        "role": "user",
                        "parts": [{"text": text}]
                    }
                ],
                "turn_complete": True
            }
        }
        await self.ws.send(json.dumps(text_message))


connections: Dict[str, GeminiConnection] = {}


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()

    try:
        gemini = GeminiConnection()
        connections[client_id] = gemini

        config_data = await websocket.receive_json()
        if config_data.get("type") != "config":
            raise ValueError("First message must be configuration")

        gemini.set_config(config_data.get("config", {}))
        await gemini.connect()

        async def receive_from_client():
            try:
                while True:
                    try:
                        if websocket.client_state.value == 3:
                            return

                        message = await websocket.receive()

                        if message["type"] == "websocket.disconnect":
                            return

                        message_content = json.loads(message["text"])
                        msg_type = message_content["type"]
                        if msg_type == "audio":
                            await gemini.send_audio(message_content["data"])
                        elif msg_type == "image":
                            await gemini.send_image(message_content["data"])
                        elif msg_type == "text":
                            await gemini.send_text(message_content["data"])
                    except json.JSONDecodeError:
                        continue
                    except KeyError:
                        continue
                    except Exception as e:
                        if "disconnect message" in str(e):
                            return
                        continue
            except Exception:
                return

        async def receive_from_gemini():
            try:
                while True:
                    if websocket.client_state.value == 3:
                        return

                    msg = await gemini.receive()
                    response = json.loads(msg)

                    try:
                        parts = response["serverContent"]["modelTurn"]["parts"]
                        for p in parts:
                            if websocket.client_state.value == 3:
                                return

                            if "inlineData" in p:
                                audio_data = p["inlineData"]["data"]
                                await websocket.send_json({
                                    "type": "audio",
                                    "data": audio_data
                                })
                            elif "text" in p:
                                await websocket.send_json({
                                    "type": "text",
                                    "data": p["text"]
                                })
                    except KeyError:
                        pass

                    try:
                        if response["serverContent"]["turnComplete"]:
                            await websocket.send_json({
                                "type": "turn_complete",
                                "data": True
                            })
                    except KeyError:
                        pass
            except Exception:
                pass

        async with asyncio.TaskGroup() as tg:
            tg.create_task(receive_from_client())
            tg.create_task(receive_from_gemini())

    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if client_id in connections:
            await connections[client_id].close()
            del connections[client_id]


def run_server(port: int = 8000):
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port)
