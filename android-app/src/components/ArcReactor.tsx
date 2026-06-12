import React, { useEffect, useRef } from "react";
import { View, Animated, Easing, StyleSheet } from "react-native";

export type ReactorState = "idle" | "listening" | "thinking" | "speaking";

interface Props {
  state: ReactorState;
  size?: number;
}

const ArcReactor: React.FC<Props> = ({ state, size = 200 }) => {
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const glowAnim = useRef(new Animated.Value(0.3)).current;
  const ringAnim = useRef(new Animated.Value(0)).current;
  const rippleAnim = useRef(new Animated.Value(0)).current;

  const center = size / 2;
  const outerR = size * 0.45;
  const innerR = size * 0.2;

  useEffect(() => {
    pulseAnim.setValue(1);
    glowAnim.setValue(0.3);
    ringAnim.setValue(0);
    rippleAnim.setValue(0);

    switch (state) {
      case "idle":
        Animated.loop(
          Animated.sequence([
            Animated.timing(pulseAnim, {
              toValue: 0.85,
              duration: 2000,
              easing: Easing.inOut(Easing.sin),
              useNativeDriver: true,
            }),
            Animated.timing(pulseAnim, {
              toValue: 1,
              duration: 2000,
              easing: Easing.inOut(Easing.sin),
              useNativeDriver: true,
            }),
          ])
        ).start();
        break;

      case "listening":
        Animated.loop(
          Animated.sequence([
            Animated.timing(pulseAnim, {
              toValue: 0.7,
              duration: 400,
              easing: Easing.inOut(Easing.sin),
              useNativeDriver: true,
            }),
            Animated.timing(pulseAnim, {
              toValue: 1,
              duration: 400,
              easing: Easing.inOut(Easing.sin),
              useNativeDriver: true,
            }),
          ])
        ).start();
        Animated.loop(
          Animated.sequence([
            Animated.timing(glowAnim, {
              toValue: 1,
              duration: 800,
              easing: Easing.linear,
              useNativeDriver: true,
            }),
            Animated.timing(glowAnim, {
              toValue: 0.3,
              duration: 800,
              easing: Easing.linear,
              useNativeDriver: true,
            }),
          ])
        ).start();
        break;

      case "thinking":
        Animated.loop(
          Animated.timing(ringAnim, {
            toValue: 1,
            duration: 1500,
            easing: Easing.linear,
            useNativeDriver: true,
          })
        ).start();
        break;

      case "speaking":
        Animated.loop(
          Animated.sequence([
            Animated.timing(rippleAnim, {
              toValue: 1,
              duration: 1200,
              easing: Easing.out(Easing.quad),
              useNativeDriver: true,
            }),
            Animated.timing(rippleAnim, {
              toValue: 0,
              duration: 0,
              useNativeDriver: true,
            }),
          ])
        ).start();
        break;
    }
  }, [state]);

  const ringRotation = ringAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ["0deg", "360deg"],
  });

  const rippleScale = rippleAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0.2, 1.5],
  });

  const rippleOpacity = rippleAnim.interpolate({
    inputRange: [0, 0.5, 1],
    outputRange: [0.8, 0.3, 0],
  });

  return (
    <View style={[styles.container, { width: size, height: size }]}>
      {/* Ripple rings (speaking state) */}
      {state === "speaking" && (
        <>
          {[0, 1, 2].map((i) => (
            <Animated.View
              key={i}
              style={[
                styles.ripple,
                {
                  width: size,
                  height: size,
                  borderRadius: size / 2,
                  borderColor: "#00BFFF",
                  opacity: rippleAnim.interpolate({
                    inputRange: [0, 1],
                    outputRange: [0.8 - i * 0.25, 0],
                  }),
                  transform: [
                    {
                      scale: rippleAnim.interpolate({
                        inputRange: [0, 1],
                        outputRange: [0.3 + i * 0.25, 1.8],
                      }),
                    },
                  ],
                },
              ]}
            />
          ))}
        </>
      )}

      {/* Outer glow */}
      <Animated.View
        style={[
          styles.glow,
          {
            width: size * 0.9,
            height: size * 0.9,
            borderRadius: (size * 0.9) / 2,
            opacity: glowAnim,
            backgroundColor: "#00BFFF",
          },
        ]}
      />

      {/* Main orb */}
      <Animated.View
        style={[
          styles.orb,
          {
            width: size * 0.6,
            height: size * 0.6,
            borderRadius: (size * 0.6) / 2,
            transform: [{ scale: pulseAnim }],
          },
        ]}
      >
        <View style={styles.orbInner}>
          {/* Center circle */}
          <View style={[styles.center, { width: innerR * 2, height: innerR * 2, borderRadius: innerR }]}>
            <View style={[styles.centerDot, { width: innerR * 0.6, height: innerR * 0.6, borderRadius: innerR * 0.3 }]} />
          </View>
        </View>
      </Animated.View>

      {/* Rotating gold ring (thinking state) */}
      {state === "thinking" && (
        <Animated.View
          style={[
            styles.ring,
            {
              width: size * 0.75,
              height: size * 0.75,
              borderRadius: (size * 0.75) / 2,
              borderColor: "#FFD700",
              transform: [{ rotate: ringRotation }],
            },
          ]}
        />
      )}

      {/* Arc segments */}
      <View style={[styles.arcs, { width: size * 0.7, height: size * 0.7 }]} pointerEvents="none">
        {[0, 120, 240].map((angle, i) => (
          <View
            key={i}
            style={[
              styles.arcSegment,
              {
                transform: [{ rotate: `${angle}deg` }],
                borderColor: state === "thinking" ? "#FFD700" : "#00BFFF",
              },
            ]}
          />
        ))}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    alignItems: "center",
    justifyContent: "center",
    position: "relative",
  },
  glow: {
    position: "absolute",
  },
  orb: {
    backgroundColor: "#003366",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 2,
    borderWidth: 2,
    borderColor: "#00BFFF",
    shadowColor: "#00BFFF",
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 20,
    elevation: 10,
  },
  orbInner: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  center: {
    backgroundColor: "#0a0a1a",
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#00BFFF",
  },
  centerDot: {
    backgroundColor: "#00BFFF",
    shadowColor: "#00BFFF",
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 10,
    elevation: 5,
  },
  ring: {
    position: "absolute",
    borderWidth: 3,
    borderLeftColor: "transparent",
    borderRightColor: "transparent",
    borderBottomColor: "transparent",
  },
  ripple: {
    position: "absolute",
    borderWidth: 2,
  },
  arcs: {
    position: "absolute",
    alignItems: "center",
    justifyContent: "center",
  },
  arcSegment: {
    position: "absolute",
    width: "100%",
    height: 2,
    top: "50%",
    borderTopWidth: 2,
    borderStyle: "dashed",
  },
});

export default ArcReactor;
