import React, { useEffect, useCallback, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  Alert,
} from "react-native";
import { useFocusEffect } from "@react-navigation/native";
import type { StackNavigationProp } from "@react-navigation/stack";
import ArcReactor, { ReactorState } from "../components/ArcReactor";
import ConnectionBadge from "../components/ConnectionBadge";
import { WebSocketService, ConnectionState } from "../services/WebSocketService";
import { VoiceService } from "../services/VoiceService";
import { StorageService, ChatMessage } from "../services/StorageService";

type Props = {
  navigation: StackNavigationProp<any>;
};

const MainScreen: React.FC<Props> = ({ navigation }) => {
  const [wsState, setWsState] = useState<ConnectionState>("disconnected");
  const [reactorState, setReactorState] = useState<ReactorState>("idle");
  const [inputText, setInputText] = useState("");
  const [transcript, setTranscript] = useState("");

  useEffect(() => {
    const unsub1 = WebSocketService.onStateChange(setWsState);
    const unsub2 = VoiceService.onStateChange((voiceState) => {
      switch (voiceState) {
        case "listening":
          setReactorState("listening");
          break;
        case "processing":
          setReactorState("thinking");
          break;
        default:
          setReactorState("idle");
      }
    });
    const unsub3 = VoiceService.onSpeech((text) => {
      setTranscript(text);
      if (text.trim()) {
        sendCommand(text.trim());
      }
    });
    const unsub4 = WebSocketService.onMessage((data) => {
      if (data.type === "response" && data.text) {
        VoiceService.speak(data.text);
        saveChatMessage({ role: "jarvis", text: data.text });
        setReactorState("idle");
      }
    });

    VoiceService.init();
    connect();

    return () => {
      unsub1();
      unsub2();
      unsub3();
      unsub4();
    };
  }, []);

  useFocusEffect(
    useCallback(() => {
      if (wsState === "disconnected") {
        connect();
      }
    }, [])
  );

  const connect = async () => {
    const settings = await StorageService.getSettings();
    if (settings.autoConnect) {
      WebSocketService.connect(settings.pcIp, settings.pcPort);
    }
  };

  const saveChatMessage = ({ role, text }: { role: "user" | "jarvis"; text: string }) => {
    const msg: ChatMessage = {
      id: Date.now().toString() + Math.random().toString(36).slice(2, 8),
      role,
      text,
      timestamp: Date.now(),
    };
    StorageService.getChatHistory().then((history) => {
      StorageService.saveChatHistory([...history, msg]);
    });
  };

  const sendCommand = (text: string) => {
    setReactorState("thinking");
    saveChatMessage({ role: "user", text });

    const sent = WebSocketService.sendCommand(text);
    if (!sent) {
      Alert.alert("Disconnected", "Not connected to PC bridge. Check settings.");
      setReactorState("idle");
    }
    setInputText("");
    setTranscript("");
  };

  const handlePushToTalk = async () => {
    if (VoiceService.state === "listening") {
      const text = await VoiceService.stopListening();
      if (text.trim()) {
        sendCommand(text.trim());
      }
    } else {
      VoiceService.startListening();
    }
  };

  const handleSendText = () => {
    if (inputText.trim()) {
      sendCommand(inputText.trim());
    }
  };

  const statusLabel = () => {
    if (wsState === "connected") return "JARVIS ONLINE";
    if (wsState === "connecting") return "CONNECTING...";
    return "JARVIS OFFLINE";
  };

  return (
    <View style={styles.container}>
      {/* Top bar */}
      <View style={styles.topBar}>
        <ConnectionBadge state={wsState} />
        <Text style={styles.statusText}>{statusLabel()}</Text>
        <View style={styles.topButtons}>
          <TouchableOpacity
            style={styles.iconBtn}
            onPress={() => navigation.navigate("Chat")}
          >
            <Text style={styles.iconText}>💬</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.iconBtn}
            onPress={() => navigation.navigate("Settings")}
          >
            <Text style={styles.iconText}>⚙</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Transcript */}
      {transcript ? (
        <Text style={styles.transcript}>"{transcript}"</Text>
      ) : null}

      {/* Arc Reactor */}
      <View style={styles.reactorContainer}>
        <ArcReactor state={reactorState} size={220} />
        <Text style={styles.tapHint}>
          {reactorState === "idle"
            ? "TAP TO TALK"
            : reactorState === "listening"
            ? "LISTENING..."
            : reactorState === "thinking"
            ? "PROCESSING..."
            : "SPEAKING..."}
        </Text>
      </View>

      {/* Push to talk button */}
      <TouchableOpacity
        style={[
          styles.talkButton,
          VoiceService.state === "listening" && styles.talkButtonActive,
        ]}
        onPress={handlePushToTalk}
        onLongPress={handlePushToTalk}
      >
        <Text style={styles.talkButtonText}>
          {VoiceService.state === "listening" ? "RELEASE TO SEND" : "HOLD TO TALK"}
        </Text>
      </TouchableOpacity>

      {/* Text input */}
      <View style={styles.inputRow}>
        <TextInput
          style={styles.textInput}
          placeholder="Type a command..."
          placeholderTextColor="#555"
          value={inputText}
          onChangeText={setInputText}
          onSubmitEditing={handleSendText}
          returnKeyType="send"
        />
        <TouchableOpacity
          style={[styles.sendBtn, !inputText.trim() && styles.sendBtnDisabled]}
          onPress={handleSendText}
          disabled={!inputText.trim()}
        >
          <Text style={styles.sendBtnText}>SEND</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0a0a1a",
    paddingTop: 50,
  },
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: "#1a1a3e",
  },
  statusText: {
    color: "#888",
    fontSize: 11,
    fontFamily: "monospace",
    marginLeft: 8,
    flex: 1,
  },
  topButtons: {
    flexDirection: "row",
  },
  iconBtn: {
    marginLeft: 8,
    padding: 6,
  },
  iconText: {
    fontSize: 20,
  },
  transcript: {
    color: "#FFD700",
    fontSize: 13,
    fontFamily: "monospace",
    textAlign: "center",
    paddingHorizontal: 20,
    paddingTop: 10,
    fontStyle: "italic",
  },
  reactorContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  tapHint: {
    color: "#555",
    fontSize: 12,
    fontFamily: "monospace",
    marginTop: 20,
    letterSpacing: 3,
  },
  talkButton: {
    alignSelf: "center",
    backgroundColor: "#003366",
    paddingHorizontal: 40,
    paddingVertical: 16,
    borderRadius: 30,
    borderWidth: 1,
    borderColor: "#00BFFF",
    marginBottom: 20,
  },
  talkButtonActive: {
    backgroundColor: "#004488",
    borderColor: "#FFD700",
  },
  talkButtonText: {
    color: "#00BFFF",
    fontSize: 14,
    fontFamily: "monospace",
    letterSpacing: 2,
  },
  inputRow: {
    flexDirection: "row",
    paddingHorizontal: 12,
    paddingBottom: 30,
    alignItems: "center",
  },
  textInput: {
    flex: 1,
    backgroundColor: "#1a1a2e",
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 12,
    color: "#FFF",
    fontSize: 15,
    fontFamily: "monospace",
    borderWidth: 1,
    borderColor: "#2a2a4e",
  },
  sendBtn: {
    marginLeft: 8,
    backgroundColor: "#003366",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "#00BFFF",
  },
  sendBtnDisabled: {
    opacity: 0.4,
  },
  sendBtnText: {
    color: "#00BFFF",
    fontSize: 12,
    fontFamily: "monospace",
    fontWeight: "bold",
  },
});

export default MainScreen;
