import React, { useEffect, useRef } from "react";
import { View, Text, StyleSheet, Animated, Easing } from "react-native";

interface Props {
  onComplete: () => void;
}

const BOOT_LINES = [
  "INITIALIZING J.A.R.V.I.S...",
  "LOADING NEURAL CORE...",
  "ESTABLISHING SECURE LINK...",
  "SYSTEMS ONLINE",
];

const SplashScreen: React.FC<Props> = ({ onComplete }) => {
  const lineAnims = useRef(BOOT_LINES.map(() => new Animated.Value(0))).current;
  const glowAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const sequence = Animated.stagger(600, lineAnims.map((anim) =>
      Animated.timing(anim, {
        toValue: 1,
        duration: 400,
        easing: Easing.out(Easing.quad),
        useNativeDriver: true,
      })
    ));

    Animated.parallel([
      sequence,
      Animated.loop(
        Animated.sequence([
          Animated.timing(glowAnim, {
            toValue: 1,
            duration: 1500,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
          Animated.timing(glowAnim, {
            toValue: 0.2,
            duration: 1500,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
        ])
      ),
    ]).start();

    const totalDuration = (BOOT_LINES.length - 1) * 600 + 400 + 1200;
    const timer = setTimeout(onComplete, totalDuration);
    return () => clearTimeout(timer);
  }, []);

  return (
    <View style={styles.container}>
      <Animated.View style={[styles.arcGlow, { opacity: glowAnim }]} />
      <View style={styles.arcRing}>
        <View style={styles.arcInner} />
      </View>
      <Text style={styles.title}>MARK XL</Text>
      <Text style={styles.subtitle}>J.A.R.V.I.S</Text>
      <View style={styles.bootLines}>
        {BOOT_LINES.map((line, i) => (
          <Animated.Text
            key={i}
            style={[
              styles.line,
              {
                opacity: lineAnims[i],
                transform: [
                  {
                    translateY: lineAnims[i].interpolate({
                      inputRange: [0, 1],
                      outputRange: [20, 0],
                    }),
                  },
                ],
              },
            ]}
          >
            {line}
          </Animated.Text>
        ))}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0a0a1a",
    alignItems: "center",
    justifyContent: "center",
    padding: 20,
  },
  arcGlow: {
    position: "absolute",
    width: 200,
    height: 200,
    borderRadius: 100,
    backgroundColor: "#00BFFF",
    top: "25%",
    opacity: 0.15,
  },
  arcRing: {
    width: 100,
    height: 100,
    borderRadius: 50,
    borderWidth: 3,
    borderColor: "#00BFFF",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 30,
    shadowColor: "#00BFFF",
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 20,
    elevation: 10,
  },
  arcInner: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: "#00BFFF",
    shadowColor: "#00BFFF",
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 15,
    elevation: 8,
  },
  title: {
    color: "#00BFFF",
    fontSize: 36,
    fontWeight: "bold",
    fontFamily: "monospace",
    letterSpacing: 8,
  },
  subtitle: {
    color: "#FFD700",
    fontSize: 14,
    fontFamily: "monospace",
    letterSpacing: 4,
    marginTop: 4,
    marginBottom: 40,
  },
  bootLines: {
    alignItems: "center",
  },
  line: {
    color: "#00BFFF",
    fontSize: 14,
    fontFamily: "monospace",
    marginVertical: 4,
    letterSpacing: 2,
  },
});

export default SplashScreen;
