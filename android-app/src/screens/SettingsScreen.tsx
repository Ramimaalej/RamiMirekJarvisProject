import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  Switch,
  TouchableOpacity,
  ScrollView,
  Alert,
} from "react-native";
import ConnectionBadge from "../components/ConnectionBadge";
import { WebSocketService, ConnectionState } from "../services/WebSocketService";
import { StorageService, AppSettings } from "../services/StorageService";

type Props = {
  navigation: any;
};

const SettingsScreen: React.FC<Props> = ({ navigation }) => {
  const [settings, setSettings] = useState<AppSettings>({
    pcIp: "",
    pcPort: "8765",
    wakeWord: "hey jarvis",
    voiceSpeed: 1.0,
    autoConnect: true,
    ttsEnabled: true,
  });
  const [wsState, setWsState] = useState<ConnectionState>("disconnected");

  useEffect(() => {
    StorageService.getSettings().then(setSettings);
    setWsState(WebSocketService.state);
    const unsub = WebSocketService.onStateChange(setWsState);
    return unsub;
  }, []);

  const updateSetting = <K extends keyof AppSettings>(
    key: K,
    value: AppSettings[K]
  ) => {
    const updated = { ...settings, [key]: value };
    setSettings(updated);
    StorageService.saveSettings(updated);
  };

  const handleConnect = async () => {
    WebSocketService.connect(settings.pcIp, settings.pcPort);
  };

  const handleDisconnect = () => {
    WebSocketService.disconnect();
  };

  const testConnection = () => {
    if (wsState === "connected") {
      const sent = WebSocketService.send({ type: "ping" });
      if (sent) {
        Alert.alert("Connected", "Jarvis bridge is reachable.");
      } else {
        Alert.alert("Error", "Could not send ping.");
      }
    } else {
      Alert.alert("Disconnected", "Connect to the bridge first.");
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.backBtn}>← BACK</Text>
        </TouchableOpacity>
        <Text style={styles.title}>SETTINGS</Text>
        <View style={{ width: 50 }} />
      </View>

      {/* Connection status */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>CONNECTION</Text>
        <View style={styles.statusRow}>
          <ConnectionBadge state={wsState} />
          <Text style={styles.statusLabel}>
            {wsState === "connected"
              ? `Connected to ${settings.pcIp}:${settings.pcPort}`
              : wsState === "connecting"
              ? "Connecting..."
              : "Not connected"}
          </Text>
        </View>
        <View style={styles.btnRow}>
          {wsState !== "connected" ? (
            <TouchableOpacity style={styles.connectBtn} onPress={handleConnect}>
              <Text style={styles.connectBtnText}>CONNECT</Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity style={styles.disconnectBtn} onPress={handleDisconnect}>
              <Text style={styles.disconnectBtnText}>DISCONNECT</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity style={styles.testBtn} onPress={testConnection}>
            <Text style={styles.testBtnText}>TEST</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* PC Bridge */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>PC BRIDGE</Text>
        <Text style={styles.label}>IP Address</Text>
        <TextInput
          style={styles.input}
          value={settings.pcIp}
          onChangeText={(t) => updateSetting("pcIp", t)}
          placeholder="192.168.1.100"
          placeholderTextColor="#444"
          keyboardType="decimal-pad"
          autoCapitalize="none"
        />
        <Text style={styles.label}>Port</Text>
        <TextInput
          style={styles.input}
          value={settings.pcPort}
          onChangeText={(t) => updateSetting("pcPort", t)}
          placeholder="8765"
          placeholderTextColor="#444"
          keyboardType="number-pad"
        />
        <View style={styles.switchRow}>
          <Text style={styles.label}>Auto-connect on start</Text>
          <Switch
            value={settings.autoConnect}
            onValueChange={(v) => updateSetting("autoConnect", v)}
            trackColor={{ false: "#333", true: "#003366" }}
            thumbColor={settings.autoConnect ? "#00BFFF" : "#666"}
          />
        </View>
      </View>

      {/* Voice */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>VOICE</Text>
        <Text style={styles.label}>Wake Word</Text>
        <TextInput
          style={styles.input}
          value={settings.wakeWord}
          onChangeText={(t) => updateSetting("wakeWord", t)}
          placeholder="hey jarvis"
          placeholderTextColor="#444"
          autoCapitalize="none"
        />
        <Text style={styles.label}>Voice Speed: {settings.voiceSpeed.toFixed(1)}x</Text>
        <View style={styles.speedRow}>
          <Text style={styles.speedLabel}>Slow</Text>
          <TouchableOpacity
            style={styles.speedBtn}
            onPress={() => updateSetting("voiceSpeed", Math.max(0.5, settings.voiceSpeed - 0.1))}
          >
            <Text style={styles.speedBtnText}>−</Text>
          </TouchableOpacity>
          <View style={styles.speedBar}>
            <View
              style={[
                styles.speedFill,
                { width: `${((settings.voiceSpeed - 0.5) / 1.5) * 100}%` },
              ]}
            />
          </View>
          <TouchableOpacity
            style={styles.speedBtn}
            onPress={() => updateSetting("voiceSpeed", Math.min(2.0, settings.voiceSpeed + 0.1))}
          >
            <Text style={styles.speedBtnText}>+</Text>
          </TouchableOpacity>
          <Text style={styles.speedLabel}>Fast</Text>
        </View>
        <View style={styles.switchRow}>
          <Text style={styles.label}>Text-to-Speech responses</Text>
          <Switch
            value={settings.ttsEnabled}
            onValueChange={(v) => updateSetting("ttsEnabled", v)}
            trackColor={{ false: "#333", true: "#003366" }}
            thumbColor={settings.ttsEnabled ? "#00BFFF" : "#666"}
          />
        </View>
      </View>

      {/* Assist App / About */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>ABOUT</Text>
        <Text style={styles.aboutText}>MARK XL v1.0.0</Text>
        <Text style={styles.aboutSub}>
          Connect your phone to your local Jarvis AI running on your PC.
        </Text>
        <TouchableOpacity
          style={styles.assistLink}
          onPress={() => {
            Alert.alert(
              "Set as Default Assist App",
              'Go to: Settings > Apps > Default Apps > Digital Assistant App\nSelect "MARK XL" to replace Google Assistant.'
            );
          }}
        >
          <Text style={styles.assistLinkText}>
            ℹ️ How to set MARK XL as default Assist app
          </Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0a0a1a",
  },
  content: {
    paddingBottom: 40,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 14,
    paddingTop: 50,
    borderBottomWidth: 1,
    borderBottomColor: "#1a1a3e",
  },
  backBtn: {
    color: "#00BFFF",
    fontSize: 13,
    fontFamily: "monospace",
  },
  title: {
    color: "#FFD700",
    fontSize: 14,
    fontFamily: "monospace",
    letterSpacing: 3,
  },
  section: {
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: "#1a1a3e",
  },
  sectionTitle: {
    color: "#FFD700",
    fontSize: 12,
    fontFamily: "monospace",
    letterSpacing: 2,
    marginBottom: 12,
  },
  statusRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 12,
  },
  statusLabel: {
    color: "#AAA",
    fontSize: 13,
    fontFamily: "monospace",
    marginLeft: 10,
  },
  btnRow: {
    flexDirection: "row",
    gap: 10,
  },
  connectBtn: {
    backgroundColor: "#003366",
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#00BFFF",
  },
  connectBtnText: {
    color: "#00BFFF",
    fontSize: 12,
    fontFamily: "monospace",
    fontWeight: "bold",
  },
  disconnectBtn: {
    backgroundColor: "#330000",
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#FF4444",
  },
  disconnectBtnText: {
    color: "#FF4444",
    fontSize: 12,
    fontFamily: "monospace",
    fontWeight: "bold",
  },
  testBtn: {
    backgroundColor: "#1a1a2e",
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#555",
  },
  testBtnText: {
    color: "#AAA",
    fontSize: 12,
    fontFamily: "monospace",
  },
  label: {
    color: "#AAA",
    fontSize: 13,
    fontFamily: "monospace",
    marginBottom: 6,
  },
  input: {
    backgroundColor: "#1a1a2e",
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    color: "#FFF",
    fontSize: 15,
    fontFamily: "monospace",
    borderWidth: 1,
    borderColor: "#2a2a4e",
    marginBottom: 12,
  },
  switchRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  speedRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 12,
  },
  speedLabel: {
    color: "#666",
    fontSize: 11,
    fontFamily: "monospace",
  },
  speedBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: "#1a1a2e",
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#2a2a4e",
    marginHorizontal: 8,
  },
  speedBtnText: {
    color: "#00BFFF",
    fontSize: 18,
    fontWeight: "bold",
  },
  speedBar: {
    flex: 1,
    height: 4,
    backgroundColor: "#2a2a4e",
    borderRadius: 2,
    overflow: "hidden",
  },
  speedFill: {
    height: "100%",
    backgroundColor: "#00BFFF",
    borderRadius: 2,
  },
  aboutText: {
    color: "#FFF",
    fontSize: 14,
    fontFamily: "monospace",
    marginBottom: 4,
  },
  aboutSub: {
    color: "#666",
    fontSize: 12,
    fontFamily: "monospace",
    lineHeight: 18,
  },
  assistLink: {
    marginTop: 12,
    padding: 10,
    backgroundColor: "#1a1a2e",
    borderRadius: 8,
    borderWidth: 1,
    borderColor: "#2a2a4e",
  },
  assistLinkText: {
    color: "#FFD700",
    fontSize: 12,
    fontFamily: "monospace",
  },
});

export default SettingsScreen;
