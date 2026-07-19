import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { colors } from '../lib/theme';

interface MatchRingProps {
  /** 0-100 */
  score: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
}

/** SVG circular progress ring showing a match score percentage — gold on navy. */
export function MatchRing({ score, size = 64, strokeWidth = 6, label }: MatchRingProps) {
  const clamped = Math.max(0, Math.min(100, score));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - clamped / 100);
  const center = size / 2;

  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <Svg width={size} height={size} style={StyleSheet.absoluteFill}>
        <Circle
          cx={center}
          cy={center}
          r={radius}
          stroke={colors.navyLight}
          strokeWidth={strokeWidth}
          fill="none"
        />
        <Circle
          cx={center}
          cy={center}
          r={radius}
          stroke={colors.gold}
          strokeWidth={strokeWidth}
          fill="none"
          strokeDasharray={`${circumference} ${circumference}`}
          strokeDashoffset={offset}
          strokeLinecap="round"
          rotation="-90"
          origin={`${center}, ${center}`}
        />
      </Svg>
      <Text style={styles.scoreText}>{Math.round(clamped)}%</Text>
      {label ? <Text style={styles.label}>{label}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  scoreText: {
    color: colors.gold,
    fontWeight: '700',
    fontSize: 14,
  },
  label: {
    color: colors.textMuted,
    fontSize: 9,
    marginTop: 1,
  },
});
