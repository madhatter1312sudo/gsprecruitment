import React from 'react';
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  ActivityIndicator,
  type TextInputProps,
  type ViewStyle,
  type StyleProp,
} from 'react-native';
import { colors, spacing, radius, typography } from '../lib/theme';

// ── Layout ──────────────────────────────────────────────────────────────

export function ScreenContainer({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.screen, style]}>{children}</View>;
}

export function Card({ children, style }: { children: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

// ── Button ──────────────────────────────────────────────────────────────

interface ButtonProps {
  title: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  disabled?: boolean;
  loading?: boolean;
  style?: StyleProp<ViewStyle>;
}

export function Button({ title, onPress, variant = 'primary', disabled, loading, style }: ButtonProps) {
  const isDisabled = disabled || loading;
  return (
    <Pressable
      onPress={onPress}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.button,
        variant === 'primary' && styles.buttonPrimary,
        variant === 'secondary' && styles.buttonSecondary,
        variant === 'ghost' && styles.buttonGhost,
        variant === 'danger' && styles.buttonDanger,
        isDisabled && styles.buttonDisabled,
        pressed && !isDisabled && styles.buttonPressed,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={variant === 'primary' ? colors.navy : colors.gold} />
      ) : (
        <Text
          style={[
            styles.buttonText,
            variant === 'primary' && styles.buttonTextPrimary,
            variant === 'secondary' && styles.buttonTextSecondary,
            variant === 'ghost' && styles.buttonTextGhost,
            variant === 'danger' && styles.buttonTextDanger,
          ]}
        >
          {title}
        </Text>
      )}
    </Pressable>
  );
}

// ── Text field ──────────────────────────────────────────────────────────

interface FieldProps extends TextInputProps {
  label?: string;
  error?: string;
}

export function TextField({ label, error, style, ...props }: FieldProps) {
  return (
    <View style={{ marginBottom: spacing.md }}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <TextInput
        placeholderTextColor={colors.textFaint}
        style={[styles.input, error && styles.inputError, style]}
        {...props}
      />
      {error ? <Text style={styles.errorText}>{error}</Text> : null}
    </View>
  );
}

// ── Chip / Badge ──────────────────────────────────────────────────────────

export function Chip({ label, tone = 'default' }: { label: string; tone?: 'default' | 'gold' | 'muted' }) {
  return (
    <View style={[styles.chip, tone === 'gold' && styles.chipGold, tone === 'muted' && styles.chipMuted]}>
      <Text style={[styles.chipText, tone === 'gold' && styles.chipTextGold]}>{label}</Text>
    </View>
  );
}

// ── States ──────────────────────────────────────────────────────────────

export function LoadingState({ label }: { label?: string }) {
  return (
    <View style={styles.centerFill}>
      <ActivityIndicator color={colors.gold} size="large" />
      {label ? <Text style={[styles.bodyMuted, { marginTop: spacing.md }]}>{label}</Text> : null}
    </View>
  );
}

export function ErrorState({ message, onRetry, retryLabel }: { message: string; onRetry?: () => void; retryLabel?: string }) {
  return (
    <View style={styles.centerFill}>
      <Text style={[styles.body, { textAlign: 'center', marginBottom: spacing.md }]}>{message}</Text>
      {onRetry ? <Button title={retryLabel ?? 'Retry'} onPress={onRetry} variant="secondary" /> : null}
    </View>
  );
}

export function EmptyState({ title, body }: { title: string; body?: string }) {
  return (
    <View style={styles.centerFill}>
      <Text style={[typography.h3, { textAlign: 'center', marginBottom: spacing.sm }]}>{title}</Text>
      {body ? <Text style={[styles.bodyMuted, { textAlign: 'center' }]}>{body}</Text> : null}
    </View>
  );
}

// ── Styles ──────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.navy,
  },
  card: {
    backgroundColor: colors.navyLight,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
  },
  button: {
    borderRadius: radius.md,
    paddingVertical: 14,
    paddingHorizontal: spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
  },
  buttonPrimary: { backgroundColor: colors.gold },
  buttonSecondary: { backgroundColor: 'transparent', borderWidth: 1.5, borderColor: colors.gold },
  buttonGhost: { backgroundColor: 'transparent' },
  buttonDanger: { backgroundColor: 'transparent', borderWidth: 1.5, borderColor: colors.danger },
  buttonDisabled: { opacity: 0.5 },
  buttonPressed: { opacity: 0.85 },
  buttonText: { ...typography.button },
  buttonTextPrimary: { color: colors.navy },
  buttonTextSecondary: { color: colors.gold },
  buttonTextGhost: { color: colors.textMuted },
  buttonTextDanger: { color: colors.danger },
  label: { color: colors.textMuted, fontSize: 13, fontWeight: '600', marginBottom: spacing.xs },
  input: {
    backgroundColor: colors.navyFaded,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
    color: colors.text,
    fontSize: 15,
  },
  inputError: { borderColor: colors.danger },
  errorText: { color: colors.danger, fontSize: 12, marginTop: spacing.xs },
  chip: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.navyFaded,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipGold: { backgroundColor: colors.goldLight, borderColor: colors.gold },
  chipMuted: { backgroundColor: 'transparent', borderColor: colors.border },
  chipText: { fontSize: 11, fontWeight: '600', color: colors.textMuted },
  chipTextGold: { color: colors.gold },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl },
  body: { ...typography.body },
  bodyMuted: { ...typography.bodyMuted },
});
