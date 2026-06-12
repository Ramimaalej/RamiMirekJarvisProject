import React from "react";
import { View, Text, StyleSheet } from "react-native";
import type { ConnectionState } from "../services/WebSocketService";

interface Props {
  state: ConnectionState;
  label?: boolean;
}

const COLORS: Record<ConnectionState, string> = {
  connected: "#00FF88",
  connecting: "#FFD700",
  disconnected: "#FF4444",
};

const LABELS: Record<ConnectionState, string> = {
  connected: "Connected",
  connecting: "Connecting...",
  disconnected: "Disconnected",
};

const ConnectionBadge: React.FC<Props> = ({ state, label = true }) => {
  return (
    <View style={styles.container}>
      <View style={[styles.dot, { backgroundColor: COLORS[state] }]} />
      {label && <Text style={[styles.label, { color: COLORS[state] }]}>{LABELS[state]}</Text>}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    shadowColor: "#00FF88",
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 4,
    elevation: 3,
  },
  label: {
    fontSize: 12,
    marginLeft: 6,
    fontFamily: "monospace",
  },
});

export default ConnectionBadge;
