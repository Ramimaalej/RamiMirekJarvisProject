export type ConnectionState = "disconnected" | "connecting" | "connected";

type MessageHandler = (data: any) => void;
type StateHandler = (state: ConnectionState) => void;

const RECONNECT_INTERVAL = 5000;

class WebSocketServiceImpl {
  private ws: WebSocket | null = null;
  private url: string = "";
  private autoReconnect: boolean = true;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private messageHandlers: Set<MessageHandler> = new Set();
  private stateHandlers: Set<StateHandler> = new Set();
  private _state: ConnectionState = "disconnected";
  private pingInterval: ReturnType<typeof setInterval> | null = null;

  get state(): ConnectionState {
    return this._state;
  }

  private setState(state: ConnectionState) {
    this._state = state;
    this.stateHandlers.forEach((h) => h(state));
  }

  onMessage(handler: MessageHandler): () => void {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }

  onStateChange(handler: StateHandler): () => void {
    this.stateHandlers.add(handler);
    return () => this.stateHandlers.delete(handler);
  }

  connect(ip: string, port: string) {
    this.url = `ws://${ip}:${port}`;
    this.autoReconnect = true;
    this.doConnect();
  }

  private doConnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.setState("connecting");

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log("[WS] Connected to", this.url);
        this.setState("connected");
        this.startPing();
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.messageHandlers.forEach((h) => h(data));
        } catch (e) {
          console.warn("[WS] Parse error:", e);
        }
      };

      this.ws.onerror = (error) => {
        console.warn("[WS] Error:", error);
      };

      this.ws.onclose = () => {
        console.log("[WS] Disconnected");
        this.setState("disconnected");
        this.stopPing();
        this.scheduleReconnect();
      };
    } catch (e) {
      console.error("[WS] Connection failed:", e);
      this.setState("disconnected");
      this.scheduleReconnect();
    }
  }

  private startPing() {
    this.stopPing();
    this.pingInterval = setInterval(() => {
      this.send({ type: "ping" });
    }, 30000);
  }

  private stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  private scheduleReconnect() {
    if (!this.autoReconnect) return;
    if (this.reconnectTimer) return;

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.autoReconnect && this._state !== "connected") {
        console.log("[WS] Reconnecting...");
        this.doConnect();
      }
    }, RECONNECT_INTERVAL);
  }

  send(data: Record<string, unknown>) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
      return true;
    }
    return false;
  }

  sendCommand(text: string): boolean {
    return this.send({ type: "command", text });
  }

  disconnect() {
    this.autoReconnect = false;
    this.stopPing();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.setState("disconnected");
  }

  get isConnected(): boolean {
    return this._state === "connected";
  }
}

export const WebSocketService = new WebSocketServiceImpl();
