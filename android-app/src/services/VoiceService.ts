import Voice, {
  SpeechResultsEvent,
  SpeechErrorEvent,
} from "@react-native-voice/voice";
import * as Speech from "expo-speech";

type VoiceState = "idle" | "listening" | "processing";

type SpeechHandler = (text: string) => void;
type StateHandler = (state: VoiceState) => void;
type ErrorHandler = (error: string) => void;

class VoiceServiceImpl {
  private _state: VoiceState = "idle";
  private speechHandlers: Set<SpeechHandler> = new Set();
  private stateHandlers: Set<StateHandler> = new Set();
  private errorHandlers: Set<ErrorHandler> = new Set();
  private _voiceSpeed: number = 1.0;

  get state(): VoiceState {
    return this._state;
  }

  private setState(state: VoiceState) {
    this._state = state;
    this.stateHandlers.forEach((h) => h(state));
  }

  setVoiceSpeed(speed: number) {
    this._voiceSpeed = speed;
  }

  onSpeech(handler: SpeechHandler): () => void {
    this.speechHandlers.add(handler);
    return () => this.speechHandlers.delete(handler);
  }

  onStateChange(handler: StateHandler): () => void {
    this.stateHandlers.add(handler);
    return () => this.stateHandlers.delete(handler);
  }

  onError(handler: ErrorHandler): () => void {
    this.errorHandlers.add(handler);
    return () => this.errorHandlers.delete(handler);
  }

  async init(): Promise<boolean> {
    try {
      Voice.onSpeechResults = this.onSpeechResults.bind(this);
      Voice.onSpeechError = this.onSpeechError.bind(this);
      Voice.onSpeechEnd = this.onSpeechEnd.bind(this);
      return true;
    } catch (e) {
      console.error("[Voice] Init error:", e);
      return false;
    }
  }

  private onSpeechResults(e: SpeechResultsEvent) {
    const text = (e.value || [])[0];
    if (text) {
      this.speechHandlers.forEach((h) => h(text));
    }
  }

  private onSpeechError(e: SpeechErrorEvent) {
    const msg = e.error?.message || "Unknown speech error";
    console.warn("[Voice] Error:", msg);
    this.errorHandlers.forEach((h) => h(msg));
    this.setState("idle");
  }

  private onSpeechEnd() {
    this.setState("idle");
  }

  async startListening(): Promise<boolean> {
    try {
      this.setState("listening");
      await Voice.start("en-US");
      return true;
    } catch (e) {
      console.error("[Voice] Start listening error:", e);
      this.setState("idle");
      return false;
    }
  }

  async stopListening(): Promise<string> {
    try {
      this.setState("processing");
      const result = await Voice.stop();
      return (result.value || [])[0] || "";
    } catch (e) {
      console.error("[Voice] Stop error:", e);
      this.setState("idle");
      return "";
    }
  }

  async destroy(): Promise<void> {
    try {
      await Voice.destroy();
    } catch (e) {
      console.error("[Voice] Destroy error:", e);
    }
    this.setState("idle");
  }

  speak(text: string): void {
    if (!text) return;
    Speech.speak(text, {
      rate: this._voiceSpeed,
      pitch: 0.9,
      language: "en-US",
    });
  }

  stopSpeaking(): void {
    Speech.stop();
  }

  isSpeaking(): boolean {
    return Speech.isSpeakingAsync();
  }
}

export const VoiceService = new VoiceServiceImpl();
