import json
import logging
import os
import threading
from typing import Any

logger = logging.getLogger("remote_control")

# Security config — override via environment variables
_ALLOWED_ORIGINS = os.environ.get("JARVIS_REMOTE_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
_API_KEY = os.environ.get("JARVIS_REMOTE_KEY", "")  # empty = no auth

_httpd = None
_thread = None

cr = {}


def _make_app():
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        return None

    app = FastAPI(title="JARVIS Remote Control")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_ALLOWED_ORIGINS,
        allow_credentials=bool(_API_KEY or len(_ALLOWED_ORIGINS) > 0),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from fastapi import Depends, HTTPException, Header

    async def _verify_key(x_api_key: str = Header(default="")) -> None:
        if _API_KEY and x_api_key != _API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/status")
    def get_status(_auth: None = Depends(_verify_key)):
        from actions.context_bus import get_bus
        ctx = get_bus().get_all()
        return {
            "status": "online",
            "context_keys": list(ctx.keys()),
            "version": "1.0",
        }

    @app.get("/api/context")
    def api_context(_auth: None = Depends(_verify_key)):
        from actions.context_bus import get_bus
        return get_bus().get_all()

    @app.post("/api/command")
    async def execute_command(body: dict, _auth: None = Depends(_verify_key)):
        command = body.get("command", "")
        args = body.get("args", {})
        if not command:
            return {"error": "No command provided"}
        result = cr.get("executor", lambda n, a: "")(command, args)
        return {"result": result}

    @app.get("/api/capabilities")
    def list_caps(_auth: None = Depends(_verify_key)):
        try:
            from actions.capability_registry import list_capabilities
            return {"capabilities": list_capabilities()}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/goals")
    def api_goals(_auth: None = Depends(_verify_key)):
        try:
            from actions.goal_engine import list_goals
            return {"goals": list_goals()}
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/monitors")
    def api_monitors(_auth: None = Depends(_verify_key)):
        try:
            from actions.monitor_manager import get_monitors
            return {"monitors": get_monitors()}
        except Exception as e:
            return {"error": str(e)}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket, x_api_key: str = Header(default="")):
        if _API_KEY and x_api_key != _API_KEY:
            await websocket.close(code=4001)
            return
        await websocket.accept()
        bus = None
        try:
            from actions.context_bus import get_bus
            bus = get_bus()
        except Exception:
            pass
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                except Exception:
                    msg = {"text": data}
                cmd = msg.get("command", msg.get("text", ""))
                args = msg.get("args", {})
                if cmd == "ping":
                    await websocket.send_json({"type": "pong"})
                elif cmd == "context":
                    ctx = bus.get_all() if bus else {}
                    entries = []
                    for k, v in ctx.items():
                        entries.append({"key": k, "value": str(v)[:200]})
                    await websocket.send_json({"type": "context", "data": entries})
                else:
                    executor = cr.get("executor")
                    if executor:
                        result = executor(cmd, args)
                        await websocket.send_json({"type": "result", "command": cmd, "result": result})
                    else:
                        await websocket.send_json({"type": "error", "message": "No executor registered"})
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        except Exception as e:
            logger.warning("WebSocket error: %s", e)

    return app


def start_server(host: str = "0.0.0.0", port: int = 8765, executor=None):
    global _httpd, _thread
    try:
        import uvicorn
    except ImportError:
        return "uvicorn not installed. Run: pip install uvicorn"

    app = _make_app()
    if app is None:
        return "FastAPI not installed. Run: pip install fastapi uvicorn"

    if executor:
        cr["executor"] = executor

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    _httpd = server
    _thread = threading.Thread(target=server.run, daemon=True)
    _thread.start()
    logger.info("Remote control server started on %s:%s", host, port)
    return f"Remote control server started on http://{host}:{port} — connect via WebSocket at ws://{host}:{port}/ws"


def stop_server():
    global _httpd, _thread
    if _httpd:
        _httpd.should_exit = True
        _httpd = None
        _thread = None
        return "Remote control server stopped."
    return "No server running."


def remote_control(
    parameters: dict[str, Any] | None = None,
    player=None,
) -> str:
    p = parameters or {}
    action = p.get("action", "start").lower()
    host = p.get("host", "0.0.0.0")
    port = int(p.get("port", 8765))

    if action == "start":
        return start_server(host=host, port=port)
    elif action == "stop":
        return stop_server()
    elif action == "status":
        if _httpd:
            import uvicorn
            return "Remote control server is running."
        return "Remote control server is not running."
    return f"Unknown action: {action}"
