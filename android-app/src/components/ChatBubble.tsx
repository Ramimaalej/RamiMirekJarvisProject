import React from "react";
import { View, Text, StyleSheet } from "react-native";
import type { ChatMessage } from "../services/StorageService";

interface Props {
  message: ChatMessage;
}

const ChatBubble: React.FC<Props> = ({ message }) => {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";
  const time = new Date(message.timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  if (isSystem) {
    return (
      <View style={styles.systemContainer}>
        <Text style={styles.systemText}>{message.text}</Text>
        <Text style={styles.systemTime}>{time}</Text>
      </View>
    );
  }

  return (
    <View style={[styles.bubbleRow, isUser ? styles.userRow : styles.jarvisRow]}>
      {!isUser && <View style={styles.avatar}><Text style={styles.avatarText}>J</Text></View>}
      <View style={[styles.bubble, isUser ? styles.userBubble : styles.jarvisBubble]}>
        <Text style={[styles.text, isUser ? styles.userText : styles.jarvisText]}>
          {message.text}
        </Text>
        <Text style={[styles.time, isUser ? styles.userTime : styles.jarvisTime]}>
          {time}
        </Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  systemContainer: {
    alignItems: "center",
    paddingVertical: 6,
  },
  systemText: {
    color: "#666",
    fontSize: 12,
    fontFamily: "monospace",
    backgroundColor: "#1a1a2e",
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 8,
    overflow: "hidden",
  },
  systemTime: {
    color: "#444",
    fontSize: 10,
    marginTop: 2,
    fontFamily: "monospace",
  },
  bubbleRow: {
    flexDirection: "row",
    marginVertical: 4,
    paddingHorizontal: 12,
    alignItems: "flex-end",
  },
  userRow: {
    justifyContent: "flex-end",
  },
  jarvisRow: {
    justifyContent: "flex-start",
  },
  avatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: "#003366",
    alignItems: "center",
    justifyContent: "center",
    marginRight: 6,
    borderWidth: 1,
    borderColor: "#00BFFF",
  },
  avatarText: {
    color: "#00BFFF",
    fontSize: 12,
    fontWeight: "bold",
    fontFamily: "monospace",
  },
  bubble: {
    maxWidth: "78%",
    padding: 12,
    borderRadius: 16,
  },
  userBubble: {
    backgroundColor: "#003366",
    borderBottomRightRadius: 4,
  },
  jarvisBubble: {
    backgroundColor: "#1a1a2e",
    borderBottomLeftRadius: 4,
    borderWidth: 1,
    borderColor: "#2a2a4e",
  },
  text: {
    fontSize: 15,
    lineHeight: 20,
  },
  userText: {
    color: "#FFFFFF",
  },
  jarvisText: {
    color: "#E0E0E0",
  },
  time: {
    fontSize: 10,
    marginTop: 4,
  },
  userTime: {
    color: "#6699cc",
    textAlign: "right",
  },
  jarvisTime: {
    color: "#555",
  },
});

export default ChatBubble;
