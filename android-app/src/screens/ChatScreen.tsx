import React, { useEffect, useState, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
} from "react-native";
import ChatBubble from "../components/ChatBubble";
import { StorageService, ChatMessage } from "../services/StorageService";
import { WebSocketService } from "../services/WebSocketService";

type Props = {
  navigation: any;
};

const ChatScreen: React.FC<Props> = ({ navigation }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const flatRef = useRef<FlatList>(null);

  useEffect(() => {
    StorageService.getChatHistory().then(setMessages);

    const unsub = WebSocketService.onMessage((data) => {
      if (data.type === "response" && data.text) {
        const msg: ChatMessage = {
          id: Date.now().toString() + Math.random().toString(36).slice(2, 8),
          role: "jarvis",
          text: data.text,
          timestamp: Date.now(),
        };
        setMessages((prev) => {
          const updated = [...prev, msg];
          StorageService.saveChatHistory(updated);
          return updated;
        });
      }
    });

    return unsub;
  }, []);

  const clearHistory = () => {
    StorageService.clearChatHistory();
    setMessages([]);
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.backBtn}>← BACK</Text>
        </TouchableOpacity>
        <Text style={styles.title}>COMMS LOG</Text>
        <TouchableOpacity onPress={clearHistory}>
          <Text style={styles.clearBtn}>CLEAR</Text>
        </TouchableOpacity>
      </View>
      <FlatList
        ref={flatRef}
        data={messages}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => <ChatBubble message={item} />}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => flatRef.current?.scrollToEnd({ animated: true })}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No messages yet.</Text>
            <Text style={styles.emptySub}>Talk to Jarvis on the main screen.</Text>
          </View>
        }
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0a0a1a",
    paddingTop: 50,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
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
  clearBtn: {
    color: "#FF4444",
    fontSize: 12,
    fontFamily: "monospace",
  },
  list: {
    paddingVertical: 12,
    flexGrow: 1,
  },
  empty: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingTop: 100,
  },
  emptyText: {
    color: "#555",
    fontSize: 16,
    fontFamily: "monospace",
  },
  emptySub: {
    color: "#444",
    fontSize: 13,
    fontFamily: "monospace",
    marginTop: 8,
  },
});

export default ChatScreen;
