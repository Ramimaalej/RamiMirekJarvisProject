import AsyncStorage from "@react-native-async-storage/async-storage";

const KEYS = {
  PC_IP: "markxl_pc_ip",
  PC_PORT: "markxl_pc_port",
  WAKE_WORD: "markxl_wake_word",
  VOICE_SPEED: "markxl_voice_speed",
  AUTO_CONNECT: "markxl_auto_connect",
  TTS_ENABLED: "markxl_tts_enabled",
};

export interface AppSettings {
  pcIp: string;
  pcPort: string;
  wakeWord: string;
  voiceSpeed: number;
  autoConnect: boolean;
  ttsEnabled: boolean;
}

const DEFAULT_SETTINGS: AppSettings = {
  pcIp: "192.168.1.100",
  pcPort: "8765",
  wakeWord: "hey jarvis",
  voiceSpeed: 1.0,
  autoConnect: true,
  ttsEnabled: true,
};

export const StorageService = {
  async getSettings(): Promise<AppSettings> {
    try {
      const json = await AsyncStorage.getItem("markxl_settings");
      if (json) {
        return { ...DEFAULT_SETTINGS, ...JSON.parse(json) };
      }
      return DEFAULT_SETTINGS;
    } catch {
      return DEFAULT_SETTINGS;
    }
  },

  async saveSettings(settings: Partial<AppSettings>): Promise<void> {
    const current = await this.getSettings();
    const merged = { ...current, ...settings };
    await AsyncStorage.setItem("markxl_settings", JSON.stringify(merged));
  },

  async getChatHistory(): Promise<ChatMessage[]> {
    try {
      const json = await AsyncStorage.getItem("markxl_chat");
      return json ? JSON.parse(json) : [];
    } catch {
      return [];
    }
  },

  async saveChatHistory(messages: ChatMessage[]): Promise<void> {
    const trimmed = messages.slice(-200);
    await AsyncStorage.setItem("markxl_chat", JSON.stringify(trimmed));
  },

  async clearChatHistory(): Promise<void> {
    await AsyncStorage.removeItem("markxl_chat");
  },
};

export interface ChatMessage {
  id: string;
  role: "user" | "jarvis" | "system";
  text: string;
  timestamp: number;
}
